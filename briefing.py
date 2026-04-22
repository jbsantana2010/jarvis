"""
briefing.py — Morning Briefing / Daily Overview aggregation for JARVIS (Sprint 9)

Gathers calendar, reminders, and Gmail into a single spoken summary.
Each section degrades gracefully if the underlying service is unavailable.

Public API:
    build_morning_briefing(anthropic_client=None) -> str
    build_whats_next()                            -> str
    build_daily_overview(anthropic_client=None)   -> str
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import reminders as _reminders
import mail_gmail
import calendar_google

log = logging.getLogger("jarvis.briefing")

USER_NAME = os.getenv("USER_NAME", "sir")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_greeting() -> str:
    h = datetime.now().hour
    if h < 12:
        return "Good morning"
    if h < 17:
        return "Good afternoon"
    return "Good evening"


def _date_str() -> str:
    return datetime.now().strftime("%A, %B %-d")


def _fmt_t(dt: datetime) -> str:
    """'3:00 PM' with no leading zero."""
    return dt.strftime("%I:%M %p").lstrip("0")


# ---------------------------------------------------------------------------
# Section gatherers — each returns data, never raises
# ---------------------------------------------------------------------------

async def _gather_calendar() -> tuple[str, Optional[object]]:
    """Return (today_summary_text, next_CalendarEvent_or_None)."""
    if not calendar_google.is_configured() or calendar_google.needs_oauth():
        return "", None
    try:
        events_today, events_next = await asyncio.gather(
            calendar_google.fetch_events("today"),
            calendar_google.fetch_events("next_event"),
            return_exceptions=True,
        )
        # Tolerate individual section failures
        if isinstance(events_today, Exception):
            events_today = []
        if isinstance(events_next, Exception):
            events_next = []

        next_ev = events_next[0] if events_next else None

        if not events_today:
            return "Your calendar is clear today.", next_ev

        n = len(events_today)
        first = events_today[0]
        first_desc = (
            f"{first.title} (all day)" if first.all_day
            else f"{first.title} at {_fmt_t(first.start)}"
        )
        ev_word = "event" if n == 1 else "events"
        if n == 1:
            return f"You have one {ev_word} today — {first_desc}.", next_ev
        return f"You have {n} {ev_word} today, starting with {first_desc}.", next_ev

    except Exception as e:
        log.debug("briefing._gather_calendar failed: %s", e)
        return "", None


def _gather_reminders_today() -> list[dict]:
    """Reminders due within the next 24 hours."""
    try:
        cutoff = (datetime.now() + timedelta(hours=24)).timestamp()
        return [r for r in _reminders.get_upcoming() if r["scheduled_ts"] <= cutoff]
    except Exception as e:
        log.debug("briefing._gather_reminders_today failed: %s", e)
        return []


async def _gather_mail() -> str:
    """Brief mail summary — unread count + top senders."""
    if not mail_gmail.is_configured() or mail_gmail.needs_oauth():
        return ""
    try:
        emails = await mail_gmail.fetch_recent_emails(max_results=10)
        if not emails:
            return "Your inbox is clear."
        unread = [e for e in emails if e.unread]
        if not unread:
            return f"No unread emails — {len(emails)} recent messages in your inbox."
        n = len(unread)
        top_names = ", ".join(e.sender for e in unread[:2])
        extra = f" and {n - 2} others" if n > 2 else ""
        return (
            f"You have {n} unread email{'s' if n != 1 else ''}, "
            f"including messages from {top_names}{extra}."
        )
    except Exception as e:
        log.debug("briefing._gather_mail failed: %s", e)
        return ""


def _fmt_reminders_brief(reminders_today: list[dict]) -> str:
    """Short spoken phrase for today's reminders."""
    if not reminders_today:
        return ""
    now = datetime.now()
    n = len(reminders_today)
    if n == 1:
        r = reminders_today[0]
        dt = datetime.fromtimestamp(r["scheduled_ts"])
        mins = int((dt - now).total_seconds() / 60)
        when = (
            f"in {mins} minute{'s' if mins != 1 else ''}" if mins < 60
            else dt.strftime("at %-I:%M %p")
        )
        return f"You have one reminder — {r['message']}, {when}."
    top = ", ".join(r["message"] for r in reminders_today[:3])
    extra = f", plus {n - 3} more" if n > 3 else ""
    return f"You have {n} reminders due today: {top}{extra}."


# ---------------------------------------------------------------------------
# Haiku polish helper — shared by briefing and overview
# ---------------------------------------------------------------------------

async def _haiku_polish(raw: str, style_hint: str, anthropic_client, max_tokens: int = 250) -> str:
    """Run raw assembled text through Haiku for natural delivery. Falls back to raw."""
    try:
        resp = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            system=(
                f"You are JARVIS, a crisp British AI butler. {style_hint} "
                "Address the user as 'sir'. No markdown, no bullet points. "
                "Spoken sentences only."
            ),
            messages=[{"role": "user", "content": raw}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        log.debug("Haiku polish failed, using raw text: %s", e)
        return raw


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_morning_briefing(anthropic_client=None) -> str:
    """Full morning briefing: greeting + calendar + reminders + mail."""
    cal_text, _next_ev = await _gather_calendar()
    mail_text = await _gather_mail()
    rem_text = _fmt_reminders_brief(_gather_reminders_today())

    greeting = f"{_time_greeting()}, {USER_NAME}. Today is {_date_str()}."
    body_parts = [p for p in [cal_text, rem_text, mail_text] if p]

    if not body_parts:
        raw = f"{greeting} Your schedule and inbox are both clear."
    else:
        raw = " ".join([greeting] + body_parts)

    if anthropic_client:
        raw = await _haiku_polish(
            raw,
            "Rewrite this daily briefing to sound natural and useful in 4-6 sentences.",
            anthropic_client,
            max_tokens=250,
        )
    return raw


async def build_whats_next() -> str:
    """The single next item — calendar event or reminder, whichever is sooner."""
    # Gather next event and next reminder concurrently
    next_event = None
    next_reminder = None

    try:
        upcoming = _reminders.get_upcoming()
        if upcoming:
            next_reminder = upcoming[0]
    except Exception:
        pass

    if calendar_google.is_configured() and not calendar_google.needs_oauth():
        try:
            events = await calendar_google.fetch_events("next_event")
            if events:
                next_event = events[0]
        except Exception:
            pass

    # Pick whichever is sooner
    if next_event and next_reminder:
        if next_event.start.timestamp() <= next_reminder["scheduled_ts"]:
            next_reminder = None
        else:
            next_event = None

    if next_event:
        return calendar_google.format_for_voice([next_event], "next_event")

    if next_reminder:
        dt = datetime.fromtimestamp(next_reminder["scheduled_ts"])
        now = datetime.now()
        mins = int((dt - now).total_seconds() / 60)
        if mins < 60:
            when = f"in {mins} minute{'s' if mins != 1 else ''}"
        elif mins < 1440:
            when = dt.strftime("at %-I:%M %p")
        else:
            when = dt.strftime("%A at %-I:%M %p")
        return f"Your next item is a reminder — {next_reminder['message']}, {when}, {USER_NAME}."

    return f"Nothing coming up, {USER_NAME}. Your schedule is clear."


async def build_daily_overview(anthropic_client=None) -> str:
    """Practical 'what to focus on today' combining calendar, reminders, and mail."""
    cal_text, _ = await _gather_calendar()
    mail_text = await _gather_mail()
    rem_text = _fmt_reminders_brief(_gather_reminders_today())

    parts = [p for p in [cal_text, rem_text, mail_text] if p]

    if not parts:
        return (
            f"Nothing on the plate today, {USER_NAME}. "
            "Calendar, reminders, and inbox are all clear."
        )

    raw = f"Daily overview for {_date_str()}: " + " ".join(parts)

    if anthropic_client:
        raw = await _haiku_polish(
            raw,
            "Summarize what this person should focus on today in 2-4 sentences. Be practical and direct.",
            anthropic_client,
            max_tokens=200,
        )
    return raw
