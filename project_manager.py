"""project_manager.py — Voice-driven project tracking for JARVIS (Sprint 14).

Stores projects, update logs, and blockers in SQLite at ~/.jarvis/projects.db.
No external dependencies. Architecture is intentionally simple so export/sync
can be layered on top later without schema changes.

Schema:
  projects         -- registry: name, status, priority, description, timestamps
  project_updates  -- append-only log of voice-logged notes per project
  project_blockers -- open/resolved blockers per project

Public API:
  All functions are synchronous. Async wrappers (async_*) are provided for
  server.py executors.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.projects")

DB_PATH = Path.home() / ".jarvis" / "projects.db"

# Status values
STATUS_ACTIVE  = "active"
STATUS_PAUSED  = "paused"
STATUS_DONE    = "done"
ALL_STATUSES   = (STATUS_ACTIVE, STATUS_PAUSED, STATUS_DONE)

# Priority values (1 = highest)
PRIORITY_HIGH   = 1
PRIORITY_MEDIUM = 2
PRIORITY_LOW    = 3
PRIORITY_LABELS = {1: "high", 2: "medium", 3: "low"}
PRIORITY_FROM_WORD = {
    "high": 1, "urgent": 1, "critical": 1, "important": 1,
    "medium": 2, "normal": 2, "default": 2,
    "low": 3, "someday": 3,
}


# ─────────────────────────────────────────────────────────────────────────────
# DB init / migration
# ─────────────────────────────────────────────────────────────────────────────

def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL COLLATE NOCASE,
                status      TEXT    NOT NULL DEFAULT 'active',
                priority    INTEGER NOT NULL DEFAULT 2,
                description TEXT    DEFAULT '',
                created_at  REAL    NOT NULL,
                updated_at  REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name
            ON projects(name COLLATE NOCASE)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_updates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                note       TEXT    NOT NULL,
                created_at REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_blockers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                description TEXT    NOT NULL,
                resolved    INTEGER NOT NULL DEFAULT 0,
                created_at  REAL    NOT NULL,
                resolved_at REAL
            )
        """)
        conn.commit()
    log.info("Projects DB ready at %s", DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy project lookup — the heart of the system
# ─────────────────────────────────────────────────────────────────────────────

def _all_project_names(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT name FROM projects WHERE status != 'done' ORDER BY updated_at DESC"
    )]


def _fuzzy_match(query: str, names: list[str]) -> tuple[Optional[str], str]:
    """
    Returns (matched_name, error_message).
    matched_name is None if no clear match.
    Priority: exact → starts-with → substring → difflib close match.
    Fails if more than one match at the winning level.
    """
    q = query.strip().lower()
    if not q:
        return None, "Please tell me which project, sir."

    # 1. Exact
    exact = [n for n in names if n.lower() == q]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, f"I found multiple projects named '{query}'. That shouldn't happen — please check the database."

    # 2. Starts-with
    starts = [n for n in names if n.lower().startswith(q)]
    if len(starts) == 1:
        return starts[0], ""
    if len(starts) > 1:
        listed = ", ".join(starts)
        return None, f"That matches multiple projects: {listed}. Be more specific, sir."

    # 3. Substring
    sub = [n for n in names if q in n.lower()]
    if len(sub) == 1:
        return sub[0], ""
    if len(sub) > 1:
        listed = ", ".join(sub)
        return None, f"That matches multiple projects: {listed}. Be more specific, sir."

    # 4. Difflib close
    close = difflib.get_close_matches(q, [n.lower() for n in names], n=1, cutoff=0.55)
    if close:
        matched_name = names[[n.lower() for n in names].index(close[0])]
        return matched_name, ""

    return None, f"I don't have a project matching '{query}', sir."


def _find_project(conn: sqlite3.Connection, query: str,
                  include_done: bool = False) -> tuple[Optional[dict], str]:
    """Resolve query to a project row dict, or return (None, error)."""
    if include_done:
        names = [row[0] for row in conn.execute("SELECT name FROM projects ORDER BY updated_at DESC")]
    else:
        names = _all_project_names(conn)
    name, err = _fuzzy_match(query, names)
    if not name:
        return None, err
    row = conn.execute(
        "SELECT id, name, status, priority, description, created_at, updated_at FROM projects WHERE name = ? COLLATE NOCASE",
        (name,)
    ).fetchone()
    if not row:
        return None, f"Project '{name}' not found, sir."
    return _row_to_dict(row), ""


def _row_to_dict(row) -> dict:
    return {
        "id": row[0], "name": row[1], "status": row[2],
        "priority": row[3], "description": row[4],
        "created_at": row[5], "updated_at": row[6],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> float:
    return time.time()


def _ago(ts: float) -> str:
    """Human-readable 'X days ago' / 'today' / 'X hours ago'."""
    delta = datetime.now() - datetime.fromtimestamp(ts)
    if delta.days == 0:
        hours = int(delta.seconds / 3600)
        if hours == 0:
            mins = int(delta.seconds / 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < 7:
        return f"{delta.days} days ago"
    if delta.days < 14:
        return "last week"
    return datetime.fromtimestamp(ts).strftime("%b %-d")


def _priority_label(p: int) -> str:
    return PRIORITY_LABELS.get(p, "medium")


# ─────────────────────────────────────────────────────────────────────────────
# Core operations
# ─────────────────────────────────────────────────────────────────────────────

def add_project(name: str, description: str = "", priority: int = PRIORITY_MEDIUM) -> tuple[bool, str]:
    """Register a new project. Fails if name already exists."""
    name = name.strip()
    if not name:
        return False, "I need a project name, sir."
    now = _now()
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            # Check for close duplicate before inserting
            existing = _all_project_names(conn)
            close = difflib.get_close_matches(name.lower(), [n.lower() for n in existing], n=1, cutoff=0.80)
            if close:
                matched = existing[[n.lower() for n in existing].index(close[0])]
                return False, f"I already have a project called '{matched}'. Did you mean that one, sir?"
            conn.execute(
                "INSERT INTO projects (name, status, priority, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, STATUS_ACTIVE, priority, description, now, now)
            )
            conn.commit()
        return True, f"Done, sir. Project '{name}' is now being tracked at {_priority_label(priority)} priority."
    except sqlite3.IntegrityError:
        return False, f"I'm already tracking a project called '{name}', sir."
    except Exception as e:
        log.error("add_project failed: %s", e)
        return False, f"Could not add project: {e}"


def get_project_status(name_query: str) -> tuple[bool, str]:
    """Full status report for a single project."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            proj, err = _find_project(conn, name_query, include_done=True)
            if not proj:
                return False, err

            pid = proj["id"]
            name = proj["name"]
            status = proj["status"]
            priority = _priority_label(proj["priority"])

            # Last update
            last = conn.execute(
                "SELECT note, created_at FROM project_updates WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                (pid,)
            ).fetchone()

            # Open blockers
            blockers = conn.execute(
                "SELECT description FROM project_blockers WHERE project_id=? AND resolved=0 ORDER BY created_at DESC",
                (pid,)
            ).fetchall()

            # Update count
            update_count = conn.execute(
                "SELECT COUNT(*) FROM project_updates WHERE project_id=?", (pid,)
            ).fetchone()[0]

            parts = [f"Project '{name}': status {status}, {priority} priority."]

            if last:
                parts.append(f"Last update {_ago(last[1])}: {last[0]}.")
            else:
                parts.append("No updates logged yet.")

            if blockers:
                bl_text = "; ".join(b[0] for b in blockers)
                parts.append(f"Open blocker{'s' if len(blockers) > 1 else ''}: {bl_text}.")
            else:
                parts.append("No open blockers.")

            if update_count:
                parts.append(f"{update_count} total update{'s' if update_count != 1 else ''} logged.")

            return True, " ".join(parts)
    except Exception as e:
        log.error("get_project_status failed: %s", e)
        return False, f"Could not get project status: {e}"


def log_update(name_query: str, note: str) -> tuple[bool, str]:
    """Append a timestamped note to a project's update log."""
    note = note.strip()
    if not note:
        return False, "I need an update note, sir."
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            proj, err = _find_project(conn, name_query)
            if not proj:
                return False, err
            now = _now()
            conn.execute(
                "INSERT INTO project_updates (project_id, note, created_at) VALUES (?, ?, ?)",
                (proj["id"], note, now)
            )
            conn.execute(
                "UPDATE projects SET updated_at=? WHERE id=?",
                (now, proj["id"])
            )
            conn.commit()
        return True, f"Logged on '{proj['name']}', sir."
    except Exception as e:
        log.error("log_update failed: %s", e)
        return False, f"Could not log update: {e}"


def add_blocker(name_query: str, description: str) -> tuple[bool, str]:
    """Add an open blocker to a project."""
    description = description.strip()
    if not description:
        return False, "I need a description of the blocker, sir."
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            proj, err = _find_project(conn, name_query)
            if not proj:
                return False, err
            conn.execute(
                "INSERT INTO project_blockers (project_id, description, created_at) VALUES (?, ?, ?)",
                (proj["id"], description, _now())
            )
            conn.execute(
                "UPDATE projects SET updated_at=? WHERE id=?",
                (_now(), proj["id"])
            )
            conn.commit()
        return True, f"Blocker noted on '{proj['name']}': {description}."
    except Exception as e:
        log.error("add_blocker failed: %s", e)
        return False, f"Could not add blocker: {e}"


def resolve_blocker(name_query: str, blocker_query: str = "") -> tuple[bool, str]:
    """Mark the best-matching open blocker as resolved."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            proj, err = _find_project(conn, name_query)
            if not proj:
                return False, err
            open_blockers = conn.execute(
                "SELECT id, description FROM project_blockers WHERE project_id=? AND resolved=0",
                (proj["id"],)
            ).fetchall()
            if not open_blockers:
                return False, f"No open blockers on '{proj['name']}', sir."
            if len(open_blockers) == 1 or not blocker_query.strip():
                bid, bdesc = open_blockers[0]
            else:
                bq = blocker_query.lower()
                match = next((b for b in open_blockers if bq in b[1].lower()), open_blockers[0])
                bid, bdesc = match
            now = _now()
            conn.execute(
                "UPDATE project_blockers SET resolved=1, resolved_at=? WHERE id=?",
                (now, bid)
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, proj["id"]))
            conn.commit()
        return True, f"Blocker resolved on '{proj['name']}': {bdesc}."
    except Exception as e:
        log.error("resolve_blocker failed: %s", e)
        return False, f"Could not resolve blocker: {e}"


def set_project_status(name_query: str, new_status: str) -> tuple[bool, str]:
    """Set project status to active/paused/done."""
    new_status = new_status.strip().lower()
    if new_status not in ALL_STATUSES:
        return False, f"Status must be active, paused, or done, sir."
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            proj, err = _find_project(conn, name_query, include_done=True)
            if not proj:
                return False, err
            conn.execute(
                "UPDATE projects SET status=?, updated_at=? WHERE id=?",
                (new_status, _now(), proj["id"])
            )
            conn.commit()
        verb = {"active": "reactivated", "paused": "paused", "done": "marked complete"}[new_status]
        return True, f"'{proj['name']}' has been {verb}, sir."
    except Exception as e:
        log.error("set_project_status failed: %s", e)
        return False, f"Could not update status: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Aggregated views
# ─────────────────────────────────────────────────────────────────────────────

def get_standup() -> tuple[bool, str]:
    """Cross-project standup: all active projects with last update and blockers."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            projects = conn.execute(
                "SELECT id, name, status, priority, updated_at FROM projects WHERE status='active' ORDER BY priority ASC, updated_at DESC"
            ).fetchall()

            if not projects:
                return True, "No active projects at the moment, sir. Say 'add project' to start tracking one."

            paused = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status='paused'"
            ).fetchone()[0]

            lines = []
            for pid, name, status, priority, updated_at in projects:
                last = conn.execute(
                    "SELECT note FROM project_updates WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                    (pid,)
                ).fetchone()
                blockers = conn.execute(
                    "SELECT COUNT(*) FROM project_blockers WHERE project_id=? AND resolved=0",
                    (pid,)
                ).fetchone()[0]
                pri_label = _priority_label(priority)
                last_update = f"Last: {last[0]}" if last else "No updates logged"
                blocker_note = f" — BLOCKED ({blockers})" if blockers else ""
                age = _ago(updated_at)
                lines.append(
                    f"{name} [{pri_label}, touched {age}]: {last_update}.{blocker_note}"
                )

            header = f"You have {len(projects)} active project{'s' if len(projects) != 1 else ''}."
            if paused:
                header += f" {paused} paused."
            return True, header + " " + " | ".join(lines)
    except Exception as e:
        log.error("get_standup failed: %s", e)
        return False, f"Could not build standup: {e}"


def get_weekly_digest() -> tuple[bool, str]:
    """Updates logged in the past 7 days, grouped by project."""
    try:
        init_db()
        since = _now() - 7 * 86400
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT p.name, u.note, u.created_at
                FROM project_updates u
                JOIN projects p ON p.id = u.project_id
                WHERE u.created_at >= ?
                ORDER BY u.created_at DESC
            """, (since,)).fetchall()

            if not rows:
                return True, "No project updates logged in the past week, sir."

            by_project: dict[str, list] = {}
            for name, note, ts in rows:
                by_project.setdefault(name, []).append((note, ts))

            parts = [f"Here is what you accomplished this week across {len(by_project)} project{'s' if len(by_project) != 1 else ''}:"]
            for name, updates in by_project.items():
                top = updates[0][0]
                extra = f" (+{len(updates)-1} more)" if len(updates) > 1 else ""
                parts.append(f"{name}: {top}{extra}.")

            return True, " ".join(parts)
    except Exception as e:
        log.error("get_weekly_digest failed: %s", e)
        return False, f"Could not build weekly digest: {e}"


def get_untouched_projects(days: int = 5) -> tuple[bool, str]:
    """Projects that haven't had any updates in the given number of days."""
    try:
        init_db()
        cutoff = _now() - days * 86400
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT name, updated_at FROM projects WHERE status='active' AND updated_at < ? ORDER BY updated_at ASC",
                (cutoff,)
            ).fetchall()
            if not rows:
                return True, f"All active projects have been touched in the last {days} days, sir."
            names = [f"{row[0]} (last touched {_ago(row[1])})" for row in rows]
            count = len(names)
            listed = "; ".join(names)
            return True, f"{count} project{'s have' if count != 1 else ' has'} gone quiet: {listed}."
    except Exception as e:
        log.error("get_untouched_projects failed: %s", e)
        return False, f"Could not check untouched projects: {e}"


def get_projects_snapshot() -> str:
    """One-line roll-up for morning briefing. Returns empty string if no active projects."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT name, priority FROM projects WHERE status='active' ORDER BY priority ASC LIMIT 5"
            ).fetchall()
            blocked = conn.execute("""
                SELECT COUNT(DISTINCT p.id)
                FROM projects p
                JOIN project_blockers b ON b.project_id = p.id
                WHERE p.status='active' AND b.resolved=0
            """).fetchone()[0]
        if not rows:
            return ""
        count = len(rows)
        top = rows[0][0]
        blocker_note = f", {blocked} blocked" if blocked else ""
        return f"{count} active project{'s' if count != 1 else ''}{blocker_note} — top priority: {top}."
    except Exception:
        return ""


def build_focus_context() -> str:
    """Return a structured text summary for Claude to reason over for focus recommendation."""
    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            projects = conn.execute(
                "SELECT id, name, priority, updated_at FROM projects WHERE status='active' ORDER BY priority ASC, updated_at ASC"
            ).fetchall()
            if not projects:
                return "No active projects."

            lines = []
            for pid, name, priority, updated_at in projects:
                last = conn.execute(
                    "SELECT note, created_at FROM project_updates WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                    (pid,)
                ).fetchone()
                blockers = conn.execute(
                    "SELECT description FROM project_blockers WHERE project_id=? AND resolved=0",
                    (pid,)
                ).fetchall()
                last_str = f"Last update {_ago(last[1])}: {last[0]}" if last else "No updates logged yet"
                blocker_str = f"BLOCKED: {'; '.join(b[0] for b in blockers)}" if blockers else "No blockers"
                pri_str = _priority_label(priority)
                lines.append(f"- {name} [{pri_str} priority] | {last_str} | {blocker_str}")

            return "\n".join(lines)
    except Exception as e:
        return f"Could not load project context: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Async wrappers for server.py executors
# ─────────────────────────────────────────────────────────────────────────────

async def async_add_project(name: str, description: str = "", priority: int = PRIORITY_MEDIUM) -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, add_project, name, description, priority)

async def async_get_project_status(name_query: str) -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, get_project_status, name_query)

async def async_log_update(name_query: str, note: str) -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, log_update, name_query, note)

async def async_add_blocker(name_query: str, description: str) -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, add_blocker, name_query, description)

async def async_resolve_blocker(name_query: str, blocker_query: str = "") -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, resolve_blocker, name_query, blocker_query)

async def async_set_project_status(name_query: str, new_status: str) -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, set_project_status, name_query, new_status)

async def async_get_standup() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, get_standup)

async def async_get_weekly_digest() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, get_weekly_digest)

async def async_get_untouched_projects() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, get_untouched_projects)
