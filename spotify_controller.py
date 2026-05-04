"""
JARVIS -- Spotify Controller (Sprint 12)

Controls Spotify playback via the Spotify Web API.
OAuth uses PKCE flow with a local callback server (same WSL2-compatible
pattern as Gmail/Calendar — bound to 0.0.0.0 so the Windows browser
can complete the flow across the WSL2 network boundary).

Setup:
  1. Go to https://developer.spotify.com/dashboard
  2. Create an app (any name) — set Redirect URI to:
       http://127.0.0.1:8888/callback
  3. Copy Client ID and Client Secret into .env

Config (.env):
  SPOTIFY_CLIENT_ID=
  SPOTIFY_CLIENT_SECRET=
  SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
  SPOTIFY_TOKEN_PATH=./token_spotify.json

Dependencies:
  pip install spotipy --break-system-packages
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("jarvis.spotify")

_HERE = Path(__file__).parent
_OAUTH_PORT = 8888
_SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
])
_VOLUME_STEP = 10   # percent per "volume up/down" command


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _client_id() -> str:
    return os.getenv("SPOTIFY_CLIENT_ID", "").strip()

def _client_secret() -> str:
    return os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

def _redirect_uri() -> str:
    return os.getenv("SPOTIFY_REDIRECT_URI", f"http://127.0.0.1:{_OAUTH_PORT}/callback").strip()

def _token_path() -> Path:
    env = os.getenv("SPOTIFY_TOKEN_PATH", "").strip()
    return Path(env) if env else _HERE / "token_spotify.json"


def is_configured() -> bool:
    """True if Client ID and Secret are both present."""
    return bool(_client_id() and _client_secret())


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

_DEPS_OK: Optional[bool] = None

def _check_deps() -> bool:
    global _DEPS_OK
    if _DEPS_OK is not None:
        return _DEPS_OK
    try:
        import spotipy  # noqa: F401
        _DEPS_OK = True
    except ImportError:
        _DEPS_OK = False
    return _DEPS_OK

def _not_configured() -> tuple[bool, str]:
    return False, (
        "Spotify isn't configured yet, sir. "
        "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your .env file — "
        "create a free app at developer.spotify.com/dashboard."
    )

def _no_deps() -> tuple[bool, str]:
    return False, (
        "The spotipy library isn't installed, sir. "
        "Run: pip install spotipy --break-system-packages"
    )

def _no_device() -> tuple[bool, str]:
    return False, (
        "No active Spotify device found, sir. "
        "Open Spotify on any device and start playing something, then try again."
    )


# ---------------------------------------------------------------------------
# OAuth / token management
# ---------------------------------------------------------------------------

def _run_oauth_flow() -> None:
    """Open browser for Spotify OAuth and save the token. Runs in a background thread."""
    if not is_configured():
        log.warning("Spotify OAuth attempted but CLIENT_ID/SECRET not set.")
        return

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        import wsgiref.simple_server
        import wsgiref.util

        sp_oauth = SpotifyOAuth(
            client_id=_client_id(),
            client_secret=_client_secret(),
            redirect_uri=_redirect_uri(),
            scope=_SCOPES,
            cache_path=str(_token_path()),
            open_browser=False,
        )

        auth_url = sp_oauth.get_authorize_url()
        log.info("Spotify OAuth: opening browser for authorization...")

        # Open browser on Windows side (works from WSL2 via explorer.exe)
        import subprocess
        subprocess.Popen(
            ["explorer.exe", auth_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Capture the OAuth callback on 0.0.0.0 so Windows browser can reach it
        captured: dict = {}

        def _wsgi_app(environ, start_response):
            qs = environ.get("QUERY_STRING", "")
            if "code=" in qs:
                raw_uri = wsgiref.util.request_uri(environ)
                captured["code"] = raw_uri
            start_response("200 OK", [("Content-Type", "text/html")])
            return [b"<html><body><h2>Spotify authentication complete.</h2>"
                    b"<p>You can close this tab and return to JARVIS.</p>"
                    b"</body></html>"]

        server = wsgiref.simple_server.make_server("0.0.0.0", _OAUTH_PORT, _wsgi_app)
        log.info("Spotify OAuth: waiting for browser callback on port %d…", _OAUTH_PORT)
        server.handle_request()
        server.server_close()

        callback_url = captured.get("code", "")
        if not callback_url:
            raise RuntimeError("OAuth callback received no auth code.")

        # Swap 0.0.0.0 → 127.0.0.1 so Spotify token endpoint accepts the redirect_uri
        callback_url = callback_url.replace(
            f"http://0.0.0.0:{_OAUTH_PORT}",
            f"http://127.0.0.1:{_OAUTH_PORT}",
            1,
        )

        code = sp_oauth.parse_response_code(callback_url)
        sp_oauth.get_access_token(code, as_dict=False)
        log.info("Spotify OAuth complete — token saved to %s", _token_path())

    except Exception as e:
        log.warning("Spotify OAuth failed: %s", e)


# ---------------------------------------------------------------------------
# Authenticated client
# ---------------------------------------------------------------------------

def _get_spotify_sync() -> Any | None:
    """Return an authenticated spotipy.Spotify client, triggering OAuth if needed.

    Returns None if not configured or deps missing.
    Triggers the OAuth flow in a background thread on first use.
    """
    if not is_configured() or not _check_deps():
        return None

    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from spotipy.exceptions import SpotifyException

    sp_oauth = SpotifyOAuth(
        client_id=_client_id(),
        client_secret=_client_secret(),
        redirect_uri=_redirect_uri(),
        scope=_SCOPES,
        cache_path=str(_token_path()),
        open_browser=False,
    )

    token_info = sp_oauth.get_cached_token()

    if not token_info:
        # Need OAuth — launch background flow and signal caller
        log.info("Spotify: no cached token, starting OAuth flow")
        t = threading.Thread(target=_run_oauth_flow, daemon=True, name="spotify-oauth")
        t.start()
        return "needs_auth"

    if sp_oauth.is_token_expired(token_info):
        try:
            token_info = sp_oauth.refresh_access_token(token_info["refresh_token"])
        except Exception as e:
            log.warning("Spotify token refresh failed: %s", e)
            return None

    return spotipy.Spotify(auth=token_info["access_token"])


async def _get_spotify() -> Any | None:
    """Async wrapper around _get_spotify_sync."""
    return await asyncio.to_thread(_get_spotify_sync)


def _active_device_id(sp) -> str | None:
    """Return the ID of the currently active Spotify device, or None."""
    try:
        devices = sp.devices()
        for d in devices.get("devices", []):
            if d.get("is_active"):
                return d["id"]
        # No active device — return first available if any
        devs = devices.get("devices", [])
        if devs:
            return devs[0]["id"]
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Playback state
# ---------------------------------------------------------------------------

async def get_status() -> tuple[bool, str]:
    """Return what's currently playing on Spotify."""
    if not is_configured():
        return _not_configured()
    if not _check_deps():
        return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp == "needs_auth":
            return None, "auth"
        if sp is None:
            return None, "error"
        try:
            current = sp.current_playback()
            return current, "ok"
        except Exception as e:
            log.warning("Spotify get_status failed: %s", e)
            return None, "error"

    current, status = await asyncio.to_thread(_run)

    if status == "auth":
        return True, "Opening Spotify sign-in in your browser, sir. Once you've approved, ask me again."
    if status == "error" or current is None:
        return False, "Spotify doesn't appear to be playing anything, sir."

    if not current.get("is_playing"):
        item = current.get("item") or {}
        name = item.get("name", "unknown")
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        return True, f"Spotify is paused on '{name}' by {artists}, sir."

    item = current.get("item") or {}
    name = item.get("name", "unknown")
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    device = current.get("device", {}).get("name", "")
    device_str = f" on {device}" if device else ""
    return True, f"Playing '{name}' by {artists}{device_str}, sir."


# ---------------------------------------------------------------------------
# Playback controls
# ---------------------------------------------------------------------------

async def play(device_id: str | None = None) -> tuple[bool, str]:
    """Resume playback."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp == "needs_auth":
            return "Opening Spotify sign-in, sir. Try again once you've approved access."
        if sp is None:
            return "Couldn't connect to Spotify, sir."
        dev = device_id or _active_device_id(sp)
        if not dev:
            return _no_device()[1]
        try:
            sp.start_playback(device_id=dev)
            return "Playing, sir."
        except Exception as e:
            msg = str(e)
            if "NO_ACTIVE_DEVICE" in msg or "404" in msg:
                return _no_device()[1]
            if "PREMIUM" in msg.upper() or "403" in msg:
                return "Spotify playback control requires a Premium account, sir."
            log.warning("Spotify play failed: %s", e)
            return "Couldn't start playback, sir."

    msg = await asyncio.to_thread(_run)
    return isinstance(msg, str) and "sir" in msg, msg


async def pause() -> tuple[bool, str]:
    """Pause playback."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp == "needs_auth":
            return "Opening Spotify sign-in, sir."
        if sp is None:
            return "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()[1]
        try:
            sp.pause_playback(device_id=dev)
            return "Paused, sir."
        except Exception as e:
            log.warning("Spotify pause failed: %s", e)
            return "Couldn't pause Spotify, sir."

    msg = await asyncio.to_thread(_run)
    return True, msg


async def skip() -> tuple[bool, str]:
    """Skip to next track."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp in ("needs_auth", None):
            return "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()[1]
        try:
            sp.next_track(device_id=dev)
            return "Skipped, sir."
        except Exception as e:
            log.warning("Spotify skip failed: %s", e)
            return "Couldn't skip the track, sir."

    msg = await asyncio.to_thread(_run)
    return True, msg


async def previous() -> tuple[bool, str]:
    """Go to previous track."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp in ("needs_auth", None):
            return "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()[1]
        try:
            sp.previous_track(device_id=dev)
            return "Going back, sir."
        except Exception as e:
            log.warning("Spotify previous failed: %s", e)
            return "Couldn't go back, sir."

    msg = await asyncio.to_thread(_run)
    return True, msg


async def set_volume(amount: str) -> tuple[bool, str]:
    """Set volume. amount: 'up', 'down', or a number 0-100."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()

    def _run():
        sp = _get_spotify_sync()
        if sp in ("needs_auth", None):
            return "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()[1]
        try:
            current = sp.current_playback()
            current_vol = 50
            if current and current.get("device"):
                current_vol = current["device"].get("volume_percent", 50) or 50

            amt = str(amount).strip().lower()
            if amt in ("up", "+"):
                new_vol = min(100, current_vol + _VOLUME_STEP)
            elif amt in ("down", "-"):
                new_vol = max(0, current_vol - _VOLUME_STEP)
            else:
                try:
                    new_vol = max(0, min(100, int(amt)))
                except ValueError:
                    return f"I didn't understand the volume amount '{amount}', sir."

            sp.volume(new_vol, device_id=dev)
            return f"Volume set to {new_vol}%, sir."
        except Exception as e:
            log.warning("Spotify volume failed: %s", e)
            return "Couldn't adjust the volume, sir."

    msg = await asyncio.to_thread(_run)
    return True, msg


# ---------------------------------------------------------------------------
# Search and queue
# ---------------------------------------------------------------------------

async def play_query(query: str) -> tuple[bool, str]:
    """Search for a track/artist/playlist and start playing it."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()
    if not query.strip():
        return False, "What would you like me to play, sir?"

    # Map common mood/genre shorthand to better search terms
    _MOOD_MAP = {
        "something chill": "chill vibes playlist",
        "focus music": "deep focus music playlist",
        "work music": "focus work music playlist",
        "workout music": "workout motivation playlist",
        "something upbeat": "upbeat feel good playlist",
        "something relaxing": "relaxing music playlist",
        "sleep music": "sleep ambient playlist",
        "lofi": "lofi hip hop beats playlist",
    }
    search_query = _MOOD_MAP.get(query.strip().lower(), query)

    def _run():
        sp = _get_spotify_sync()
        if sp == "needs_auth":
            return False, "Opening Spotify sign-in, sir. Try again once approved."
        if sp is None:
            return False, "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()

        try:
            # Try track first, then artist, then playlist
            results = sp.search(q=search_query, limit=5, type="track,artist,playlist")

            # Prefer a direct track match
            tracks = results.get("tracks", {}).get("items", [])
            artists = results.get("artists", {}).get("items", [])
            playlists = results.get("playlists", {}).get("items", [])

            # Playlist-style queries → prefer playlist
            is_playlist_query = any(w in search_query.lower()
                                    for w in ("playlist", "mix", "vibes", "music", "beats", "ambient"))

            if is_playlist_query and playlists:
                pl = playlists[0]
                sp.start_playback(device_id=dev, context_uri=pl["uri"])
                return True, f"Playing the '{pl['name']}' playlist, sir."

            # Artist query → play top tracks
            if artists and not tracks:
                artist = artists[0]
                sp.start_playback(device_id=dev, context_uri=artist["uri"])
                return True, f"Playing {artist['name']}, sir."

            # Track match
            if tracks:
                track = tracks[0]
                name = track["name"]
                artist_name = track["artists"][0]["name"] if track["artists"] else ""
                sp.start_playback(device_id=dev, uris=[track["uri"]])
                return True, f"Playing '{name}' by {artist_name}, sir."

            # Artist fallback
            if artists:
                artist = artists[0]
                sp.start_playback(device_id=dev, context_uri=artist["uri"])
                return True, f"Playing {artist['name']}, sir."

            return False, f"Couldn't find anything for '{query}', sir."

        except Exception as e:
            msg = str(e)
            if "PREMIUM" in msg.upper() or "403" in msg:
                return False, "Spotify playback control requires a Premium account, sir."
            if "NO_ACTIVE_DEVICE" in msg or "404" in msg:
                return _no_device()
            log.warning("Spotify play_query failed: %s", e)
            return False, "Couldn't play that, sir — Spotify may not be open."

    return await asyncio.to_thread(_run)


async def queue_query(query: str) -> tuple[bool, str]:
    """Search for a track and add it to the queue."""
    if not is_configured(): return _not_configured()
    if not _check_deps(): return _no_deps()
    if not query.strip():
        return False, "What would you like me to queue, sir?"

    def _run():
        sp = _get_spotify_sync()
        if sp in ("needs_auth", None):
            return False, "Couldn't connect to Spotify, sir."
        dev = _active_device_id(sp)
        if not dev:
            return _no_device()
        try:
            results = sp.search(q=query, limit=1, type="track")
            tracks = results.get("tracks", {}).get("items", [])
            if not tracks:
                return False, f"Couldn't find a track matching '{query}', sir."
            track = tracks[0]
            sp.add_to_queue(track["uri"], device_id=dev)
            name = track["name"]
            artist_name = track["artists"][0]["name"] if track["artists"] else ""
            return True, f"Queued '{name}' by {artist_name}, sir."
        except Exception as e:
            log.warning("Spotify queue failed: %s", e)
            return False, "Couldn't add that to the queue, sir."

    return await asyncio.to_thread(_run)
