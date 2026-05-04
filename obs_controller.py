"""
JARVIS -- OBS Studio Controller (Sprint 10)

Connects to OBS via WebSocket v5 protocol using obsws-python.
Lazy connection: connects on first command, reuses afterward.
Fails gracefully if OBS is not running -- never crashes, never hangs.

Configuration (from .env):
  OBS_WEBSOCKET_PORT=4455
  OBS_WEBSOCKET_PASSWORD=          # leave blank for no auth

All public functions are async and safe to call from the voice loop.
"""

import os
import asyncio
import logging
from typing import Any

log = logging.getLogger("jarvis.obs")

# obsws_python prints the full connection traceback at WARNING level on every
# failed attempt — suppress it so the JARVIS log stays readable.
for _lg in (
    "obsws_python",
    "obsws_python.baseclient.ObsClient",
    "websocket",
    "websocket-client",
):
    _l = logging.getLogger(_lg)
    _l.setLevel(logging.CRITICAL)
    _l.disabled = True


# ---------------------------------------------------------------------------
# WSL2 host detection
# ---------------------------------------------------------------------------

def _get_windows_host_ip() -> str:
    """Return the Windows host IP when running inside WSL2.

    Uses the default route gateway (e.g. 172.27.32.1), which is the actual
    Windows host in NAT-mode WSL2. Falls back to the /etc/resolv.conf
    nameserver, then 'localhost', on any error.
    """
    import subprocess as _sp2

    # Primary: default route gateway — the real Windows host in NAT-mode WSL2
    try:
        r = _sp2.run(
            ["bash", "-c", "ip route | awk '/^default/ {print $3; exit}'"],
            capture_output=True, text=True, timeout=3,
        )
        ip = r.stdout.strip()
        if ip:
            return ip
    except Exception:
        pass

    # Fallback: DNS nameserver from /etc/resolv.conf
    try:
        r = _sp2.run(
            ["bash", "-c", "grep nameserver /etc/resolv.conf | awk '{print $2}' | head -1"],
            capture_output=True, text=True, timeout=3,
        )
        ip = r.stdout.strip()
        if ip:
            return ip
    except Exception:
        pass

    return "localhost"


import platform as _plat
_is_wsl = "microsoft" in _plat.uname().release.lower()

# ---------------------------------------------------------------------------
# Config -- read once at import time (env already loaded by server.py)
# ---------------------------------------------------------------------------

OBS_HOST = (
    _get_windows_host_ip()
    if _is_wsl
    else os.getenv("OBS_WEBSOCKET_HOST", "localhost")
)
OBS_PORT     = int(os.getenv("OBS_WEBSOCKET_PORT", "4455"))
OBS_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")
CONNECT_TIMEOUT = 3  # seconds -- keeps commands snappy even when OBS is closed

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_client: Any = None          # obsws_python.ReqClient once connected
_lock: asyncio.Lock | None = None  # created lazily inside the event loop


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def _get_client() -> Any | None:
    """Return a connected OBS client, or None if OBS is not reachable.

    On first call: attempts connection.
    On success: caches the client for reuse.
    On failure: returns None -- callers report 'OBS not running'.
    """
    global _client
    async with _get_lock():
        if _client is not None:
            return _client
        try:
            import obsws_python as obs
            # ReqClient.__init__ is blocking -- run in thread to not block event loop
            client = await asyncio.to_thread(
                obs.ReqClient,
                host=OBS_HOST,
                port=OBS_PORT,
                password=OBS_PASSWORD,
                timeout=CONNECT_TIMEOUT,
            )
            _client = client
            log.info(f"OBS connected at {OBS_HOST}:{OBS_PORT}")
            return _client
        except Exception as exc:
            log.info(f"OBS not reachable: {exc}")
            return None


async def _call(method: str, *args, **kwargs) -> Any | None:
    """Call an OBS API method safely.

    Returns the response object, or None on any failure.
    Resets the cached client so the next call will reconnect
    (handles the case where OBS was closed mid-session).
    """
    global _client
    client = await _get_client()
    if client is None:
        return None
    try:
        fn = getattr(client, method)
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        log.warning(f"OBS call '{method}' failed: {exc}")
        _client = None   # force reconnect on next command
        return None


def _not_running() -> tuple[bool, str]:
    return False, "OBS doesn't appear to be running, sir. Please open OBS first."


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

async def get_status() -> dict | None:
    """Return current OBS state as a dict, or None if OBS is not running.

    Keys: streaming (bool), recording (bool), scene (str),
          stream_timecode (str|None), record_timecode (str|None)
    """
    stream_resp  = await _call("get_stream_status")
    if stream_resp is None:
        return None
    record_resp  = await _call("get_record_status")
    scene_resp   = await _call("get_current_program_scene")

    return {
        "streaming":        getattr(stream_resp,  "output_active",   False),
        "recording":        getattr(record_resp,  "output_active",   False) if record_resp else False,
        "scene":            getattr(scene_resp,   "current_program_scene_name", "unknown") if scene_resp else "unknown",
        "stream_timecode":  getattr(stream_resp,  "output_timecode", None),
        "record_timecode":  getattr(record_resp,  "output_timecode", None) if record_resp else None,
    }


def format_status(s: dict) -> str:
    """Convert a status dict to a voice-friendly string."""
    live_str = "live and streaming" if s["streaming"] else "not streaming"
    rec_str  = ", recording" if s["recording"] else ""
    scene_str = f" Current scene: {s['scene']}."

    if s["streaming"] and s.get("stream_timecode"):
        tc = s["stream_timecode"].split(".")[0]   # drop milliseconds
        uptime = f" Uptime: {tc}."
    else:
        uptime = ""

    return f"You are {live_str}{rec_str}, sir.{scene_str}{uptime}"


# ---------------------------------------------------------------------------
# Stream control
# ---------------------------------------------------------------------------

async def start_stream() -> tuple[bool, str]:
    """Start streaming. Returns (success, message)."""
    status = await get_status()
    if status is None:
        return _not_running()
    if status["streaming"]:
        return True, "You're already live, sir."
    result = await _call("start_stream")
    if result is None:
        return False, "I couldn't start the stream, sir. OBS may have reported an error."
    return True, "Stream started. You're live, sir."


async def stop_stream() -> tuple[bool, str]:
    """Stop streaming. Returns (success, message)."""
    status = await get_status()
    if status is None:
        return _not_running()
    if not status["streaming"]:
        return True, "You're not currently streaming, sir."
    result = await _call("stop_stream")
    if result is None:
        return False, "I couldn't stop the stream, sir."
    return True, "Stream stopped. You're no longer live, sir."


# ---------------------------------------------------------------------------
# Recording control
# ---------------------------------------------------------------------------

async def start_recording() -> tuple[bool, str]:
    """Start recording. Returns (success, message)."""
    status = await get_status()
    if status is None:
        return _not_running()
    if status["recording"]:
        return True, "Already recording, sir."
    result = await _call("start_record")
    if result is None:
        return False, "I couldn't start the recording, sir."
    return True, "Recording started, sir."


async def stop_recording() -> tuple[bool, str]:
    """Stop recording. Returns (success, message)."""
    status = await get_status()
    if status is None:
        return _not_running()
    if not status["recording"]:
        return True, "You're not currently recording, sir."
    result = await _call("stop_record")
    if result is None:
        return False, "I couldn't stop the recording, sir."
    return True, "Recording stopped, sir."


# ---------------------------------------------------------------------------
# Scene control
# ---------------------------------------------------------------------------

async def get_scene_names() -> list[str] | None:
    """Return list of scene names from OBS, or None if not connected."""
    resp = await _call("get_scene_list")
    if resp is None:
        return None
    scenes = getattr(resp, "scenes", [])
    # scenes is a list of dicts; key is 'sceneName'
    return [s.get("sceneName", s.get("scene_name", "")) for s in scenes if s]


async def list_scenes() -> tuple[bool, str]:
    """Return a voice-friendly list of scenes."""
    names = await get_scene_names()
    if names is None:
        return _not_running()
    if not names:
        return True, "No scenes found in OBS, sir."
    count = len(names)
    joined = ", ".join(names)
    return True, f"You have {count} scene{'s' if count != 1 else ''}, sir: {joined}."


async def switch_scene(query: str) -> tuple[bool, str]:
    """Switch to the scene that best matches query.

    Matching priority:
      1. Exact match (case-insensitive)
      2. Scene name contains query as substring
      3. All query words found in scene name
      4. Any query word found in scene name (best hit by word coverage)
    """
    names = await get_scene_names()
    if names is None:
        return _not_running()
    if not names:
        return False, "No scenes available in OBS, sir."

    q = query.strip().lower()
    q_words = q.split()

    # 1. Exact match
    match = next((n for n in names if n.lower() == q), None)

    # 2. Substring
    if not match:
        match = next((n for n in names if q in n.lower()), None)

    # 3. All query words present
    if not match:
        match = next((n for n in names
                      if all(w in n.lower() for w in q_words)), None)

    # 4. Best coverage: most query words found
    if not match and q_words:
        scored = sorted(
            names,
            key=lambda n: sum(1 for w in q_words if w in n.lower()),
            reverse=True,
        )
        if sum(1 for w in q_words if w in scored[0].lower()) > 0:
            match = scored[0]

    if not match:
        names_str = ", ".join(names)
        return False, (
            f"I couldn't find a scene matching '{query}', sir. "
            f"Available scenes: {names_str}."
        )

    result = await _call("set_current_program_scene", match)
    if result is None:
        return False, f"I found scene '{match}' but couldn't switch to it, sir."
    return True, f"Switched to {match}, sir."


# ---------------------------------------------------------------------------
# Audio / mic control
# ---------------------------------------------------------------------------

async def _get_mic_input_name() -> str | None:
    """Find the name of the first configured microphone input.

    Tries get_special_inputs() first (mic_1), then falls back
    to scanning all inputs for anything with 'mic' in the name.
    """
    # Try special inputs (fastest path)
    special = await _call("get_special_inputs")
    if special is not None:
        mic_name = getattr(special, "mic_1", None)
        if mic_name:
            return mic_name

    # Fall back: scan all inputs
    inputs_resp = await _call("get_input_list")
    if inputs_resp is None:
        return None
    inputs = getattr(inputs_resp, "inputs", [])
    for inp in inputs:
        name = inp.get("inputName", inp.get("input_name", ""))
        if "mic" in name.lower() or "microphone" in name.lower():
            return name
    return None


async def toggle_mic() -> tuple[bool, str]:
    """Toggle the mute state of the primary microphone input."""
    mic_name = await _get_mic_input_name()
    if mic_name is None:
        # Check if OBS is even reachable
        if await get_status() is None:
            return _not_running()
        return False, "I couldn't find a microphone input in OBS, sir."

    result = await _call("toggle_input_mute", mic_name)
    if result is None:
        return False, f"I couldn't toggle the mic, sir."

    # toggle_input_mute returns the NEW mute state
    now_muted = getattr(result, "input_muted", None)
    if now_muted is True:
        return True, "Microphone muted, sir."
    elif now_muted is False:
        return True, "Microphone unmuted, sir."
    else:
        return True, "Microphone toggled, sir."
