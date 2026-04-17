"""
mail_gmail.py — Gmail API integration for JARVIS (read-only, Sprint 7)

Dependencies (install once):
    pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages

Setup:
    1. Go to https://console.cloud.google.com
    2. Create a project → enable the Gmail API
    3. Configure OAuth consent screen (External, add your Gmail as test user)
    4. Create OAuth 2.0 credentials → Desktop app → download credentials.json
    5. Place credentials.json in the JARVIS project folder (same dir as server.py)
    6. First use triggers a browser OAuth flow — token.json is saved automatically
    7. Add to .env (optional — defaults work if files are in project folder):
         GMAIL_CREDENTIALS_PATH=./credentials.json
         GMAIL_TOKEN_PATH=./token.json
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ---------------------------------------------------------------------------
# Lazy dependency check — fails only when Gmail is actually used
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
# Config paths (overridable via .env)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent  # always the jarvis project folder
_OAUTH_PORT = 9877              # fixed port for OAuth local redirect server


def _creds_path() -> Path:
    env = os.getenv("GMAIL_CREDENTIALS_PATH", "")
    return Path(env) if env else _HERE / "credentials.json"


def _token_path() -> Path:
    env = os.getenv("GMAIL_TOKEN_PATH", "")
    return Path(env) if env else _HERE / "token.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class EmailMessage:
    sender: str       # display name or email local-part
    subject: str
    snippet: str      # Gmail's auto-generated preview text
    timestamp: str    # human-readable, e.g. "Mon Apr 13, 02:30 PM"
    unread: bool
    message_id: str

# ---------------------------------------------------------------------------
# Auth + service builder (synchronous — called via run_in_executor)
# ---------------------------------------------------------------------------

def needs_oauth() -> bool:
    """True if an OAuth browser flow is required (no token, or token invalid/expired)."""
    tp = _token_path()
    if not tp.exists():
        return True
    if not _check_deps():
        return False  # can't check, assume ok and let _build_service_sync handle it
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(tp), SCOPES)
        # Valid and not expired → no OAuth needed
        if creds and creds.valid:
            return False
        # Expired but refreshable → no browser needed, refresh inline
        if creds and creds.expired and creds.refresh_token:
            return False
        return True
    except Exception:
        return True


def trigger_oauth_background() -> None:
    """Open Windows browser for OAuth and save token.json when done.

    Returns immediately — auth runs in a daemon thread. The voice loop is
    never blocked. Next call to fetch_recent_emails() will find the token.
    """
    import threading
    import subprocess as _sp
    import platform as _plat

    def _auth_thread():
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(_creds_path()), SCOPES)
            # Pre-set redirect_uri to our fixed port so we know the URL before starting
            flow.redirect_uri = f"http://localhost:{_OAUTH_PORT}/"
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

            # Open in Windows browser (works from WSL via PowerShell)
            _sp.run(
                ["powershell.exe", "Start-Process", auth_url],
                check=False, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
            )
            log.info("Gmail OAuth: browser opened, waiting for user approval…")

            # Wait for OAuth redirect (blocks this thread only, not the voice loop)
            creds = flow.run_local_server(port=_OAUTH_PORT, open_browser=False)
            _token_path().write_text(creds.to_json())
            log.info("Gmail OAuth complete — token saved to %s", _token_path())
        except Exception as e:
            log.warning("Gmail OAuth background thread failed: %s", e)

    t = threading.Thread(target=_auth_thread, daemon=True, name="gmail-oauth")
    t.start()


def _build_service_sync():
    """Build an authenticated Gmail API service. Raises descriptively on any failure."""
    if not _check_deps():
        raise RuntimeError(
            "Gmail libraries not installed. Run: "
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
            f"Gmail credentials not found at '{cp}'. "
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
                log.info("Gmail token refreshed")
            except Exception as e:
                tp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Gmail token expired and refresh failed: {e}. "
                    "Say 'check my email' again to re-authenticate."
                ) from e
        else:
            # Should not reach here if callers check needs_oauth() first
            raise RuntimeError(
                "Gmail token missing or invalid. Say 'check my email' to authenticate."
            )

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_sender(raw: str) -> str:
    """'John Smith <john@example.com>' → 'John Smith', else email local-part."""
    name, addr = parseaddr(raw)
    if name:
        return name.strip()
    if addr:
        return addr.split("@")[0]
    return raw[:40]


def _parse_message(msg: dict) -> EmailMessage:
    """Parse a Gmail message resource (metadata format) into EmailMessage."""
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    try:
        ts = datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000)
        timestamp = ts.strftime("%a %b %d, %I:%M %p")
    except Exception:
        timestamp = "unknown time"

    snippet = (msg.get("snippet", "")
               .replace("&#39;", "'")
               .replace("&amp;", "&")
               .replace("&lt;", "<")
               .replace("&gt;", ">"))

    return EmailMessage(
        sender=_short_sender(headers.get("from", "Unknown")),
        subject=headers.get("subject", "(no subject)"),
        snippet=snippet,
        timestamp=timestamp,
        unread="UNREAD" in msg.get("labelIds", []),
        message_id=msg.get("id", ""),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """True if credentials.json exists in the expected location."""
    return _creds_path().exists()


def _fetch_sync(max_results: int) -> list[EmailMessage]:
    """Blocking fetch — run this via run_in_executor."""
    service = _build_service_sync()
    result = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results,
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        return []

    emails = []
    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            emails.append(_parse_message(msg))
        except Exception as e:
            log.warning("Skipping message %s: %s", msg_ref.get("id"), e)
    return emails


async def fetch_recent_emails(max_results: int = 10) -> list[EmailMessage]:
    """Async: fetch recent inbox messages. Times out after 15 s. Raises on failure."""
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _fetch_sync, max_results),
        timeout=15.0,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_for_voice(emails: list[EmailMessage]) -> str:
    """2–3 sentence spoken summary — brief enough to be read aloud."""
    if not emails:
        return "Inbox is clear, sir."
    unread = [e for e in emails if e.unread]
    total = len(emails)
    if unread:
        intro = (f"You have {len(unread)} unread message"
                 f"{'s' if len(unread) != 1 else ''} out of {total} recent.")
    else:
        intro = f"No unread messages — {total} recent in your inbox."
    top = (unread[:3] if unread else emails[:3])
    details = "; ".join(f"{e.sender} — {e.subject[:50]}" for e in top)
    return f"{intro} Most recent: {details}."


def format_for_llm(emails: list[EmailMessage]) -> str:
    """Structured text for feeding to Claude Haiku for summarization."""
    lines = [f"Gmail inbox — {len(emails)} most recent messages:"]
    for e in emails:
        status = "UNREAD" if e.unread else "read"
        lines.append(
            f"[{status}] {e.timestamp} | From: {e.sender} | "
            f"Subject: {e.subject} | Preview: {e.snippet[:150]}"
        )
    return "\n".join(lines)


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
        return "the Gmail API quota has been exceeded"
    if "libraries not installed" in msg:
        return "the Gmail libraries are not installed"
    return "the connection failed"
