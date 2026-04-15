"""
JARVIS — Reminder System

Stores and manages time-based reminders in SQLite.
Design mirrors conversation_db: stdlib only, non-blocking, simple schema.

Schema:
  id           — autoincrement PK
  message      — what to remind about
  scheduled_ts — unix timestamp when to fire
  status       — 'pending' | 'done' | 'cancelled'
  created_ts   — when the reminder was created
"""

import sqlite3
import time
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jarvis.reminders")

DB_PATH = Path.home() / ".jarvis" / "reminders.db"


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create reminders table if it doesn't exist."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    message      TEXT    NOT NULL,
                    scheduled_ts REAL    NOT NULL,
                    status       TEXT    NOT NULL DEFAULT 'pending',
                    created_ts   REAL    NOT NULL
                )
            """)
            conn.commit()
        log.info(f"Reminders DB ready at {DB_PATH}")
    except Exception as e:
        log.error(f"reminders init_db failed: {e}")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def add_reminder(message: str, scheduled_ts: float) -> int:
    """Store a new reminder. Returns the new row id, or -1 on failure."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO reminders (message, scheduled_ts, status, created_ts) "
                "VALUES (?, ?, 'pending', ?)",
                (message, scheduled_ts, time.time()),
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


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_due(now: float | None = None) -> list[dict]:
    """Return all pending reminders whose scheduled_ts <= now."""
    if now is None:
        now = time.time()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, message, scheduled_ts FROM reminders "
                "WHERE status='pending' AND scheduled_ts <= ? "
                "ORDER BY scheduled_ts",
                (now,),
            ).fetchall()
        return [{"id": r[0], "message": r[1], "scheduled_ts": r[2]} for r in rows]
    except Exception as e:
        log.error(f"reminders get_due failed: {e}")
        return []


def get_upcoming() -> list[dict]:
    """Return all future pending reminders (up to 20)."""
    now = time.time()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, message, scheduled_ts FROM reminders "
                "WHERE status='pending' AND scheduled_ts > ? "
                "ORDER BY scheduled_ts LIMIT 20",
                (now,),
            ).fetchall()
        return [{"id": r[0], "message": r[1], "scheduled_ts": r[2]} for r in rows]
    except Exception as e:
        log.error(f"reminders get_upcoming failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

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

    # "at H[:MM] [AM|PM]" — with optional "tomorrow" prefix
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
            # No meridiem + low number → assume PM (e.g. "at 6" → 18:00)
            hour += 12

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if tomorrow:
            target += timedelta(days=1)
        elif target <= now:
            # Already passed today — schedule for tomorrow
            target += timedelta(days=1)
        return target

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

        parts.append(f"{r['message']} — {when}")

    count = len(parts)
    intro = f"You have {count} pending reminder{'s' if count != 1 else ''}, sir."
    return intro + " " + ". ".join(parts) + "."
