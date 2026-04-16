"""
JARVIS -- Reminder System

Stores and manages time-based reminders in SQLite.
Design mirrors conversation_db: stdlib only, non-blocking, simple schema.

Sprint 9: added cancel, snooze, recurring reminders.

Schema:
  id                -- autoincrement PK
  message           -- what to remind about
  scheduled_ts      -- unix timestamp when to fire next
  status            -- 'pending' | 'done' | 'cancelled'
  created_ts        -- when the reminder was created
  recurrence_type   -- NULL | 'daily' | 'weekdays' | 'weekly'
  recurrence_value  -- NULL | weekday name for 'weekly' (e.g. 'monday')
  last_triggered_at -- unix timestamp of last fire, NULL if never fired
"""

import sqlite3
import time
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jarvis.reminders")

DB_PATH = Path.home() / ".jarvis" / "reminders.db"

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# ---------------------------------------------------------------------------
# Init / migration
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create reminders table if it doesn't exist; migrate existing DBs."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    message           TEXT    NOT NULL,
                    scheduled_ts      REAL    NOT NULL,
                    status            TEXT    NOT NULL DEFAULT 'pending',
                    created_ts        REAL    NOT NULL,
                    recurrence_type   TEXT,
                    recurrence_value  TEXT,
                    last_triggered_at REAL
                )
            """)
            # Migrate existing DBs that were created before Sprint 9
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
            for col, defn in [
                ("recurrence_type",   "TEXT"),
                ("recurrence_value",  "TEXT"),
                ("last_triggered_at", "REAL"),
            ]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE reminders ADD COLUMN {col} {defn}")
                    log.info(f"Migrated reminders DB: added column {col}")
            conn.commit()
        log.info(f"Reminders DB ready at {DB_PATH}")
    except Exception as e:
        log.error(f"reminders init_db failed: {e}")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def add_reminder(message: str, scheduled_ts: float,
                 recurrence_type: str | None = None,
                 recurrence_value: str | None = None) -> int:
    """Store a new reminder. Returns the new row id, or -1 on failure."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO reminders "
                "(message, scheduled_ts, status, created_ts, recurrence_type, recurrence_value) "
                "VALUES (?, ?, 'pending', ?, ?, ?)",
                (message, scheduled_ts, time.time(), recurrence_type, recurrence_value),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        log.error(f"reminders add_reminder failed: {e}")
        return -1


def mark_done(reminder_id: int) -> None:
    """Mark a reminder as done so it never fires again."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE reminders SET status='done' WHERE id=?", (reminder_id,)
            )
            conn.commit()
    except Exception as e:
        log.error(f"reminders mark_done failed: {e}")


def cancel_reminder(query: str) -> dict | None:
    """Cancel the best-matching pending reminder.

    Match priority:
      1. Exact message match (case-insensitive)
      2. Message contains the query substring
      3. Most recently created pending reminder (fallback / empty query)

    Returns the cancelled reminder dict, or None if nothing matched.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = query.strip().lower()

            rows = conn.execute(
                "SELECT id, message, scheduled_ts, recurrence_type FROM reminders "
                "WHERE status='pending' ORDER BY created_ts DESC"
            ).fetchall()

            if not rows:
                return None

            # 1. Exact match
            match = next((r for r in rows if r["message"].lower() == q), None)
            # 2. Substring match
            if not match and q:
                match = next((r for r in rows if q in r["message"].lower()), None)
            # 3. Most recent
            if not match:
                match = rows[0]

            conn.execute(
                "UPDATE reminders SET status='cancelled' WHERE id=?", (match["id"],)
            )
            conn.commit()
            log.info(f"Cancelled reminder {match['id']}: '{match['message']}'")
            return dict(match)
    except Exception as e:
        log.error(f"reminders cancel_reminder failed: {e}")
        return None


def snooze_reminder(reminder_id: int, delta_seconds: float) -> dict | None:
    """Push a reminder forward by delta_seconds from now.

    Works on both pending and done reminders (supports post-fire snooze).
    Returns the updated reminder dict, or None on failure.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, message, scheduled_ts FROM reminders WHERE id=?",
                (reminder_id,)
            ).fetchone()
            if not row:
                return None
            new_ts = time.time() + delta_seconds
            conn.execute(
                "UPDATE reminders SET scheduled_ts=?, status='pending' WHERE id=?",
                (new_ts, reminder_id)
            )
            conn.commit()
            log.info(
                f"Snoozed reminder {reminder_id} by {delta_seconds:.0f}s "
                f"-> {datetime.fromtimestamp(new_ts)}"
            )
            return {"id": row["id"], "message": row["message"], "scheduled_ts": new_ts}
    except Exception as e:
        log.error(f"reminders snooze_reminder failed: {e}")
        return None


def find_reminder(query: str) -> dict | None:
    """Find the best matching pending reminder without modifying it.

    Uses the same priority as cancel_reminder: exact -> substring -> most recent.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            q = query.strip().lower()
            rows = conn.execute(
                "SELECT id, message, scheduled_ts FROM reminders "
                "WHERE status='pending' ORDER BY created_ts DESC"
            ).fetchall()
            if not rows:
                return None
            match = next((r for r in rows if r["message"].lower() == q), None)
            if not match and q:
                match = next((r for r in rows if q in r["message"].lower()), None)
            if not match:
                match = rows[0]
            return dict(match)
    except Exception as e:
        log.error(f"reminders find_reminder failed: {e}")
        return None


def reschedule_recurring(reminder: dict) -> bool:
    """Compute and set the next occurrence for a recurring reminder.

    Updates scheduled_ts and last_triggered_at; keeps status 'pending'.
    Returns True if rescheduled, False if not recurring or on error.
    """
    rec_type = reminder.get("recurrence_type")
    if not rec_type:
        return False
    try:
        current_dt = datetime.fromtimestamp(reminder["scheduled_ts"])
        next_dt = _next_occurrence(current_dt, rec_type, reminder.get("recurrence_value"))
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE reminders "
                "SET scheduled_ts=?, status='pending', last_triggered_at=? "
                "WHERE id=?",
                (next_dt.timestamp(), time.time(), reminder["id"])
            )
            conn.commit()
        log.info(f"Recurring reminder {reminder['id']} rescheduled -> {next_dt}")
        return True
    except Exception as e:
        log.error(f"reminders reschedule_recurring failed: {e}")
        return False


def _next_occurrence(dt: datetime, recurrence_type: str,
                     recurrence_value: str | None) -> datetime:
    """Return the next datetime after dt for the given recurrence pattern."""
    if recurrence_type == "daily":
        return dt + timedelta(days=1)

    if recurrence_type == "weekdays":
        # Advance day by day until we land on Mon-Fri
        next_dt = dt + timedelta(days=1)
        while next_dt.weekday() >= 5:  # 5=Sat, 6=Sun
            next_dt += timedelta(days=1)
        return next_dt

    if recurrence_type == "weekly":
        # Same time, exactly one week later
        return dt + timedelta(weeks=1)

    # Unknown type -- fall back to daily
    return dt + timedelta(days=1)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_due(now: float | None = None) -> list[dict]:
    """Return all pending reminders whose scheduled_ts <= now."""
    if now is None:
        now = time.time()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, message, scheduled_ts, recurrence_type, recurrence_value "
                "FROM reminders "
                "WHERE status='pending' AND scheduled_ts <= ? "
                "ORDER BY scheduled_ts",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"reminders get_due failed: {e}")
        return []


def get_upcoming() -> list[dict]:
    """Return all future pending reminders (up to 20)."""
    now = time.time()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, message, scheduled_ts, recurrence_type, recurrence_value "
                "FROM reminders "
                "WHERE status='pending' AND scheduled_ts > ? "
                "ORDER BY scheduled_ts LIMIT 20",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"reminders get_upcoming failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Time & recurrence parsing
# ---------------------------------------------------------------------------

def parse_recurrence(text: str) -> tuple[str | None, str | None, str]:
    """Parse a recurrence prefix from a SET_REMINDER time expression.

    Supported patterns (case-insensitive):
      "every day at X"       -> ("daily",    None,      "at X")
      "daily at X"           -> ("daily",    None,      "at X")
      "every weekday at X"   -> ("weekdays", None,      "at X")
      "every monday at X"    -> ("weekly",   "monday",  "at X")

    Returns (recurrence_type, recurrence_value, remaining_time_expr).
    If no recurrence is found, returns (None, None, original_text).
    """
    t = text.strip().lower()

    # "every day ..." or "daily ..."
    m = re.match(r'(?:every\s+day|daily)\s+(.*)', t)
    if m:
        return "daily", None, m.group(1).strip()

    # "every weekday ..."
    m = re.match(r'every\s+weekday\s+(.*)', t)
    if m:
        return "weekdays", None, m.group(1).strip()

    # "every <weekday-name> ..."
    days_pattern = "|".join(WEEKDAY_MAP.keys())
    m = re.match(rf'every\s+({days_pattern})\s+(.*)', t)
    if m:
        return "weekly", m.group(1).strip(), m.group(2).strip()

    return None, None, text


def parse_time(text: str) -> datetime | None:
    """Parse a natural language time expression into an absolute datetime.

    Supported formats:
      "in N seconds"              (for testing)
      "in N minutes / mins"
      "in N hours / hrs"
      "at H[:MM] [AM|PM]"
      "tomorrow at H[:MM] [AM|PM]"

    Returns None if the expression cannot be parsed.
    """
    now = datetime.now()
    t = text.strip().lower()

    # "in N seconds"
    m = re.search(r'in\s+(\d+)\s+second', t)
    if m:
        return now + timedelta(seconds=int(m.group(1)))

    # "in N minutes"
    m = re.search(r'in\s+(\d+)\s+(minute|minutes|min|mins)', t)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "in N hours"
    m = re.search(r'in\s+(\d+)\s+(hour|hours|hr|hrs)', t)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # "at H[:MM] [AM|PM]" -- with optional "tomorrow" prefix
    tomorrow = "tomorrow" in t
    m = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', t)
    if m:
        hour   = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        merid  = m.group(3)

        if merid == "pm" and hour != 12:
            hour += 12
        elif merid == "am" and hour == 12:
            hour = 0
        elif merid is None and 1 <= hour <= 7:
            # No meridiem + low number -> assume PM (e.g. "at 6" -> 18:00)
            hour += 12

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if tomorrow:
            target += timedelta(days=1)
        elif target <= now:
            # Already passed today -- schedule for tomorrow
            target += timedelta(days=1)
        return target

    return None


def parse_snooze_duration(text: str) -> float | None:
    """Parse a snooze duration string into seconds.

    Examples:
      "5 minutes"  -> 300.0
      "10 mins"    -> 600.0
      "1 hour"     -> 3600.0
      "30 seconds" -> 30.0

    Returns None if unparseable.
    """
    t = text.strip().lower()

    m = re.search(r'(\d+)\s+second', t)
    if m:
        return float(m.group(1))

    m = re.search(r'(\d+)\s+(minute|minutes|min|mins)', t)
    if m:
        return float(m.group(1)) * 60

    m = re.search(r'(\d+)\s+(hour|hours|hr|hrs)', t)
    if m:
        return float(m.group(1)) * 3600

    return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_upcoming(upcoming: list[dict]) -> str:
    """Format a list of upcoming reminders as a voice-friendly string."""
    if not upcoming:
        return "You have no pending reminders, sir."

    now = datetime.now()
    parts = []
    for r in upcoming:
        dt    = datetime.fromtimestamp(r["scheduled_ts"])
        delta = dt - now
        mins  = int(delta.total_seconds() / 60)

        if mins < 60:
            when = f"in {mins} minute{'s' if mins != 1 else ''}"
        elif mins < 1440:
            hrs = round(delta.total_seconds() / 3600, 1)
            when = f"in {hrs} hour{'s' if hrs != 1.0 else ''}"
        else:
            when = dt.strftime("%A at %-I:%M %p")

        rec = r.get("recurrence_type")
        if rec == "daily":
            rec_str = ", repeating daily"
        elif rec == "weekdays":
            rec_str = ", repeating on weekdays"
        elif rec == "weekly":
            day = (r.get("recurrence_value") or "").title()
            rec_str = f", repeating every {day}" if day else ", repeating weekly"
        else:
            rec_str = ""

        parts.append(f"{r['message']} -- {when}{rec_str}")

    count = len(parts)
    intro = f"You have {count} pending reminder{'s' if count != 1 else ''}, sir."
    return intro + " " + ". ".join(parts) + "."
