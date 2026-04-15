"""
JARVIS — Conversation Persistence

Stores recent conversation history in a local SQLite database so JARVIS
remembers context across server restarts.

Design principles:
- Zero dependencies (stdlib sqlite3 only)
- Non-blocking: all I/O is fast enough to run inline (tiny rows, small table)
- Capped: never grows beyond MAX_STORED_MESSAGES rows
- Simple: one table, no schemas to migrate
"""

import sqlite3
import time
import logging
from pathlib import Path

log = logging.getLogger("jarvis.conversation_db")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = Path.home() / ".jarvis" / "conversations.db"
MAX_STORED_MESSAGES = 200   # hard cap on rows kept in DB
LOAD_ON_STARTUP = 20        # messages injected into history on new connection


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the database and table if they don't exist yet."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    session   TEXT    NOT NULL,
                    role      TEXT    NOT NULL,
                    content   TEXT    NOT NULL,
                    ts        REAL    NOT NULL
                )
            """)
            conn.commit()
        log.info(f"Conversation DB ready at {DB_PATH}")
    except Exception as e:
        log.error(f"conversation_db init_db failed: {e}")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_recent(limit: int = LOAD_ON_STARTUP) -> list[dict]:
    """Return the most recent `limit` messages in chronological order.

    Called once at WebSocket connect so JARVIS picks up where it left off.
    Returns [] if DB is missing or empty.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """SELECT role, content
                   FROM messages
                   ORDER BY ts DESC, id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        # Reverse → oldest first (chronological)
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception as e:
        log.warning(f"conversation_db load_recent failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_turn(session: str, user_text: str, assistant_text: str) -> None:
    """Persist one user/assistant exchange.

    Called after every successful response.  Runs synchronously — the SQLite
    write for two tiny rows takes < 1 ms and never blocks the event loop
    noticeably.
    """
    now = time.time()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO messages (session, role, content, ts) VALUES (?, ?, ?, ?)",
                [
                    (session, "user",      user_text,      now),
                    (session, "assistant", assistant_text, now + 0.001),
                ],
            )
            conn.commit()
    except Exception as e:
        log.warning(f"conversation_db save_turn failed: {e}")


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------

def prune(keep: int = MAX_STORED_MESSAGES) -> None:
    """Delete old rows keeping only the most recent `keep` messages.

    Called once at startup after init_db() to keep the file small.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                DELETE FROM messages
                WHERE id NOT IN (
                    SELECT id FROM messages
                    ORDER BY ts DESC, id DESC
                    LIMIT ?
                )
            """, (keep,))
            conn.commit()
    except Exception as e:
        log.warning(f"conversation_db prune failed: {e}")
