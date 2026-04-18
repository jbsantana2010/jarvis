"""
calendar_google.py — Google Calendar integration for JARVIS (read-only, Sprint 8)

Reuses the same credentials.json already in use for Gmail.
Stores a separate token (token_calendar.json) to keep scopes independent.

Dependencies (already installed with Gmail):
    pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages

Setup:
    1. Go to https://console.cloud.google.com → your existing JARVIS project
    2. Enable the Google Calendar API  (APIs & Services → Library → "Google Calendar API")
    3. No new credentials needed — same credentials.json works
    4. First use opens a browser OAuth flow — token_calendar.json is saved automatically
    5. Optional .env overrides:
         GCAL_TOKEN_PATH=./token_calendar.json   # where to save the Calendar token
         USER_TIMEZONE=America/New_York           # IANA timezone; defaults to system local
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# ---------------------------------------------------------------------------
# Lazy dependency check
# ---------------------------------------------------------------------------

_DEPS_OK: Optional[bool] = None


def _check_deps() -> bool:
    global _DEPS_OK
    if _DEPS_OK is not None:
        return _DEPS_OK
    try:
        import google.oauth2.credentials          # noqa: F401
        import google_auth_oauthlib.flow          # noqa: F401
        import google.auth.transport.requests     # noqa: F401
        import googleapiclient.discovery          # noqa: F401
        _DEPS_OK = True
    except ImportError:
        _DEPS_OK = False
    return _DEPS_OK


# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
_OAUTH_PORT = 9878   # distinct from Gmail's 9877


def _creds_path() -> Path:
    """Reuse the same credentials.json as Gmail — same Google project."""
    env = os.getenv("GMAIL_CREDENTIALS_PATH", "")
    return Path(env) if env else _HERE / "credentials.json"


def _token_path() -> Path:
    env = os.getenv("GCAL_TOKEN_PATH", "")
    return Path(env) if env else _HERE / "token_calendar.json"


def _local_now() -> datetime:
    """Return current datetime in the user's local timezone."""
    tz_name = os.getenv("USER_TIMEZONE", "").strip()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(tz=ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now().astimezone()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    location: str
    all_day: bool
    description: str


# ---------------------------------------------------------------------------
# Auth (mirrors mail_gmail.py pattern exactly)
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """True if credentials.json exists."""
    return _creds_path().exists()


def needs_oauth() -> bool:
    """True if a browser OAuth flow is required."""
    tp = _token_path()
    if not tp.exists():
        return True
    if not _check_deps():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(tp), SCOPES)
        if creds and creds.valid:
            return False
        if creds and creds.expired and creds.refresh_token:
            return False
        return True
    except Exception:
        return True


def trigger_oauth_background() -> None:
    """Open Windows browser for Calendar OAuth and save token_calendar.json.

    Returns immediately — runs in a daemon thread, never blocks the voice loop.
    """
    import threading
    import subprocess as _sp

    def _auth_thread():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(_creds_path()), SCOPES)
            flow.redirect_uri = f"http://localhost:{_OAUTH_PORT}/"
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

            safe_url = auth_url.replace("'", "")
            _sp.run(
                ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{safe_url}'"],
                check=False, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
            )
            log.info("Calendar OAuth: browser opened, waiting for approval…")

            import wsgiref.simple_server
            import wsgiref.util

            captured: dict = {}

            def _wsgi_app(environ, start_response):
                qs = environ.get("QUERY_STRING", "")
                if "code=" in qs:
                    raw_uri = wsgiref.util.request_uri(environ)
                    captured["auth_response"] = raw_uri.replace(
                        f"http://0.0.0.0:{_OAUTH_PORT}",
                        f"http://localhost:{_OAUTH_PORT}",
                        1,
                    )
                start_response("200 OK", [("Content-Type", "text/html")])
                return [b"<html><body><h2>Calendar authentication complete.</h2>"
                        b"<p>You can close this tab and return to JARVIS.</p>"
                        b"</body></html>"]

            server = wsgiref.simple_server.make_server("0.0.0.0", _OAUTH_PORT, _wsgi_app)
            server.handle_request()
            server.server_close()

            auth_response = captured.get("auth_response", "")
            if not auth_response:
                raise RuntimeError("Calendar OAuth callback received no auth code.")

            import os as _os
            _os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
            flow.fetch_token(authorization_response=auth_response)
            _os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)

            creds = flow.credentials
            _token_path().write_text(creds.to_json())
            log.info("Calendar OAuth complete — token saved to %s", _token_path())
        except Exception as e:
            log.warning("Calendar OAuth background thread failed: %s", e)

    t = threading.Thread(target=_auth_thread, daemon=True, name="gcal-oauth")
    t.start()


def _build_service_sync():
    """Build an authenticated Calendar API service. Raises descriptively on failure."""
    if not _check_deps():
        raise RuntimeError(
            "Google libraries not installed. Run: "
            "pip install google-auth-oauthlib google-auth-httplib2 "
            "google-api-python-client --break-system-packages"
        )

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    cp = _creds_path()
    tp = _token_path()

    if not cp.exists():
        raise FileNotFoundError(
            f"Google credentials not found at '{cp}'. "
            "Download credentials.json from Google Cloud Console "
            "and place it in the JARVIS project folder."
        )

    creds = None
    if tp.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tp), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                tp.write_text(creds.to_json())
                log.info("Calendar token refreshed")
            except Exception as e:
                tp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Calendar token expired and refresh failed: {e}. "
                    "Say 'what's on my calendar' again to re-authenticate."
                ) from e
        else:
            raise RuntimeError(
                "Calendar token missing or invalid. Say 'what's on my calendar' to authenticate."
            )

    return build("calendar", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Time windows
# ---------------------------------------------------------------------------

def _window_for_range(range_str: str) -> tuple[datetime, datetime, int]:
    """Return (time_min, time_max, max_results) for a named range string."""
    now = _local_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    r = range_str.strip().lower()

    if r in ("today", ""):
        return today_start, today_start + timedelta(days=1), 20

    if r == "tomorrow":
        t = today_start + timedelta(days=1)
        return t, t + timedelta(days=1), 20

    if r in ("this_afternoon", "afternoon"):
        start = max(now, today_start.replace(hour=12))
        end = today_start.replace(hour=18)
        if start >= end:
            # Afternoon already passed — return empty window
            return now, now, 0
        return start, end, 20

    if r in ("this_evening", "evening"):
        start = max(now, today_start.replace(hour=18))
        end = today_start + timedelta(days=1)
        if start >= end:
            return now, now, 0
        return start, end, 20

    if r in ("this_week", "week"):
        return now, today_start + timedelta(days=7), 30

    if r in ("next_event", "next"):
        return now, today_start + timedelta(days=7), 1

    # Fallback — treat as today
    return today_start, today_start + timedelta(days=1), 20


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------

def _parse_event(item: dict) -> Optional[CalendarEvent]:
    """Parse a Google Calendar event resource into a CalendarEvent."""
    try:
        title = item.get("summary", "(no title)").strip()
        if not title:
            title = "(no title)"

        start_raw = item.get("start", {})
        end_raw   = item.get("end", {})

        all_day = "date" in start_raw and "dateTime" not in start_raw

        if all_day:
            start_str = start_raw.get("date", "")
            end_str   = end_raw.get("date", "")
            # Parse as naive date, localise to midnight in local tz
            start_dt = datetime.fromisoformat(start_str).replace(
                tzinfo=_local_now().tzinfo
            )
            end_dt = datetime.fromisoformat(end_str).replace(
                tzinfo=_local_now().tzinfo
            )
        else:
            start_dt = datetime.fromisoformat(start_raw.get("dateTime", ""))
            end_dt   = datetime.fromisoformat(end_raw.get("dateTime", ""))

        location = item.get("location", "").strip()
        description = (item.get("description", "") or "").strip()[:200]

        return CalendarEvent(
            title=title,
            start=start_dt,
            end=end_dt,
            location=location,
            all_day=all_day,
            description=description,
        )
    except Exception as e:
        log.debug("Skipping unparseable event %s: %s", item.get("id"), e)
        return None


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _fetch_sync(range_str: str) -> list[CalendarEvent]:
    """Blocking fetch — run via run_in_executor."""
    time_min, time_max, max_results = _window_for_range(range_str)

    if max_results == 0:
        return []  # empty window (e.g. afternoon already passed)

    service = _build_service_sync()
    result = service.events().list(
        calendarId="primary",
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for item in result.get("items", []):
        ev = _parse_event(item)
        if ev is not None:
            events.append(ev)
    return events


async def fetch_events(range_str: str = "today") -> list[CalendarEvent]:
    """Async: fetch calendar events for the given range. Times out after 15 s."""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _fetch_sync, range_str),
        timeout=15.0,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_time(dt: datetime) -> str:
    """Format a datetime as a natural spoken time: '3:00 PM' or '3:30 PM'."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _fmt_date(dt: datetime) -> str:
    """Format a date for reference: 'Monday', 'Tuesday', etc."""
    return dt.strftime("%A")


def _describe_event(ev: CalendarEvent, include_day: bool = False) -> str:
    """One-phrase description of an event for spoken output."""
    day_prefix = f"{_fmt_date(ev.start)}, " if include_day else ""
    if ev.all_day:
        return f"{day_prefix}{ev.title} (all day)"
    return f"{day_prefix}{ev.title} at {_fmt_time(ev.start)}"


def format_for_voice(events: list[CalendarEvent], range_str: str = "today") -> str:
    """Convert a list of events to a natural spoken summary."""
    r = range_str.strip().lower() or "today"

    # Label for empty responses
    _EMPTY = {
        "today":           "Your day is clear, sir.",
        "tomorrow":        "Tomorrow is clear, sir.",
        "this_afternoon":  "Your afternoon is clear, sir.",
        "afternoon":       "Your afternoon is clear, sir.",
        "this_evening":    "Your evening is clear, sir.",
        "evening":         "Your evening is clear, sir.",
        "this_week":       "Nothing on the calendar this week, sir.",
        "week":            "Nothing on the calendar this week, sir.",
        "next_event":      "Nothing coming up in the next seven days, sir.",
        "next":            "Nothing coming up in the next seven days, sir.",
    }

    if not events:
        return _EMPTY.get(r, "Nothing found, sir.")

    n = len(events)

    # Next event — single-event special case
    if r in ("next_event", "next"):
        ev = events[0]
        now = _local_now()
        delta = ev.start - now
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            time_part = "right now"
        elif minutes < 60:
            time_part = f"in {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = minutes // 60
            mins_rem = minutes % 60
            if mins_rem == 0:
                time_part = f"in {hours} hour{'s' if hours != 1 else ''}"
            else:
                time_part = f"in {hours}h {mins_rem}m"
            if ev.all_day:
                time_part = _fmt_date(ev.start)

        if ev.all_day:
            return f"Your next event is {ev.title} on {_fmt_date(ev.start)}, sir."
        return f"Your next event is {ev.title} at {_fmt_time(ev.start)}, {time_part}, sir."

    # This week — group by day
    if r in ("this_week", "week"):
        from collections import defaultdict
        by_day: dict = defaultdict(list)
        for ev in events:
            by_day[ev.start.date()].append(ev)

        now = _local_now()
        parts = []
        for day_date in sorted(by_day):
            day_events = by_day[day_date]
            day_dt = datetime.combine(day_date, datetime.min.time()).replace(
                tzinfo=now.tzinfo
            )
            if day_date == now.date():
                day_label = "Today"
            else:
                day_label = _fmt_date(day_dt)
            descs = ", ".join(_describe_event(e) for e in day_events)
            ev_word = "event" if len(day_events) == 1 else "events"
            parts.append(f"{day_label} has {len(day_events)} {ev_word}: {descs}")

        total_word = "event" if n == 1 else "events"
        intro = f"You have {n} {total_word} this week, sir. "
        return intro + "; ".join(parts) + "."

    # Today / tomorrow / afternoon / evening
    if r in ("today", ""):
        period = "today"
    elif r == "tomorrow":
        period = "tomorrow"
    elif r in ("this_afternoon", "afternoon"):
        period = "this afternoon"
    elif r in ("this_evening", "evening"):
        period = "this evening"
    else:
        period = "coming up"

    ev_word = "event" if n == 1 else "events"
    intro = f"You have {n} {ev_word} {period}, sir."

    if n == 1:
        ev = events[0]
        detail = _describe_event(ev)
        loc = f" At {ev.location}." if ev.location else ""
        return f"{intro} {detail}.{loc}"

    # Multiple events — list up to 4
    shown = events[:4]
    descs = "; ".join(_describe_event(e) for e in shown)
    tail = f" Plus {n - 4} more." if n > 4 else ""
    return f"{intro} {descs}.{tail}"


def friendly_error(exc: Exception) -> str:
    """Convert common exceptions to natural spoken error phrases."""
    msg = str(exc)
    if isinstance(exc, FileNotFoundError) or "credentials not found" in msg.lower():
        return "the credentials file is missing, sir"
    if "token" in msg.lower() and ("expired" in msg.lower() or "refresh" in msg.lower()):
        return "the auth token expired — re-authentication required"
    if isinstance(exc, asyncio.TimeoutError) or "timed out" in msg.lower():
        return "the request timed out"
    if "quota" in msg.lower():
        return "the Calendar API quota has been exceeded"
    if "libraries not installed" in msg:
        return "the Google libraries are not installed"
    return "the connection failed"
