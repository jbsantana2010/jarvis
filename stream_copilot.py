"""
JARVIS -- Stream Copilot (Sprint 11)

High-level streaming macros that orchestrate multiple OBS actions
in the correct order with safety checks and smart scene detection.

Configuration (from .env):
  STREAM_STARTING_SCENE=     # Scene shown during countdown/intro (e.g. "Starting Soon")
  STREAM_GAMEPLAY_SCENE=     # Main content scene after going live (e.g. "Gameplay")
  STREAM_BRB_SCENE=          # BRB / Away scene (e.g. "BRB")
  STREAM_ENDING_SCENE=       # Outro / ending scene (e.g. "Ending")
  STREAM_SAFE_SCENE=         # Fallback scene for panic (defaults to starting scene)
  STREAM_DASHBOARD_URL=      # URL to open in browser on stream prep (optional)
  STREAM_AUTO_RECORD=true    # Start recording automatically alongside stream
  STREAM_BRB_MUTES_MIC=true  # Mute mic when entering BRB mode
  STREAM_PANIC_STOPS_STREAM=false  # true = panic ends stream; false = cuts to safe scene
  OBS_MIC_INPUT_NAME=        # Override mic input name (auto-detected if blank)
"""

import asyncio
import logging
import os

import obs_controller

log = logging.getLogger("jarvis.stream_copilot")


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_bool(key: str, default: bool = True) -> bool:
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    return val not in ("false", "0", "no", "off")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _find_scene(env_key: str, *keywords: str) -> str | None:
    """Return a scene name by checking env config first, then fuzzy-matching keywords.

    Priority:
      1. Exact match against env_key value (case-insensitive).
      2. Substring match against env_key value.
      3. Keyword scan across all scene names (first keyword wins).
    Returns None if OBS is unreachable or no scene matches.
    """
    configured = _env(env_key)
    names = await obs_controller.get_scene_names()
    if names is None:
        return None

    if configured:
        exact = next((n for n in names if n.lower() == configured.lower()), None)
        if exact:
            return exact
        substr = next((n for n in names if configured.lower() in n.lower()), None)
        if substr:
            return substr

    for kw in keywords:
        match = next((n for n in names if kw.lower() in n.lower()), None)
        if match:
            return match

    return None


async def _set_mic_muted(muted: bool) -> None:
    """Explicitly set the primary mic to muted/unmuted (not a toggle)."""
    mic_name = await obs_controller._get_mic_input_name()
    if mic_name is None:
        return
    current = await obs_controller._call("get_input_mute", mic_name)
    if current is None:
        return
    currently_muted = getattr(current, "input_muted", False)
    if currently_muted != muted:
        await obs_controller._call("set_input_mute", mic_name, muted)


async def _ensure_obs_running() -> tuple[bool, str | None]:
    """Check OBS is reachable. Returns (ok, error_message_or_None)."""
    status = await obs_controller.get_status()
    if status is None:
        return False, (
            "Can't reach OBS, sir — WebSocket isn't responding. "
            "Please open OBS and enable WebSocket Server under "
            "Tools → WebSocket Server Settings."
        )
    return True, None


# ---------------------------------------------------------------------------
# Macro: stream_prep
# ---------------------------------------------------------------------------

async def stream_prep() -> tuple[bool, str]:
    """Pre-stream checklist (does NOT go live):
      1. Verify OBS is reachable.
      2. Switch to the starting/holding scene.
      3. Unmute mic (ensure hot before going live).
      4. Start recording if STREAM_AUTO_RECORD=true.

    Returns (success, voice_message).
    """
    ok, err = await _ensure_obs_running()
    if not ok:
        return False, err

    steps: list[str] = []

    scene = await _find_scene(
        "STREAM_STARTING_SCENE",
        "starting", "start", "waiting", "lobby", "holding", "countdown", "soon",
    )
    if scene:
        result = await obs_controller._call("set_current_program_scene", scene)
        if result is not None:
            steps.append(f"switched to {scene}")
    else:
        steps.append("no starting scene configured")

    await _set_mic_muted(False)
    steps.append("mic unmuted")

    if _env_bool("STREAM_AUTO_RECORD", default=True):
        status = await obs_controller.get_status()
        if status and not status["recording"]:
            rec = await obs_controller._call("start_record")
            if rec is not None:
                steps.append("recording started")

    summary = ", ".join(steps)
    return True, f"Stream prep complete, sir — {summary}. Ready when you are."


# ---------------------------------------------------------------------------
# Macro: go_live
# ---------------------------------------------------------------------------

async def go_live() -> tuple[bool, str]:
    """Full go-live sequence:
      1. Confirm OBS is reachable and not already live.
      2. Start the OBS stream.
      3. Start recording if STREAM_AUTO_RECORD=true and not already recording.
      4. Switch to the gameplay/main scene after a brief stabilisation pause.

    Returns (success, voice_message).
    """
    ok, err = await _ensure_obs_running()
    if not ok:
        return False, err

    status = await obs_controller.get_status()
    if status is None:
        return False, "OBS doesn't appear to be running, sir."
    if status["streaming"]:
        return True, "You're already live, sir."

    _, stream_msg = await obs_controller.start_stream()
    if "couldn't" in stream_msg.lower() or "error" in stream_msg.lower():
        return False, stream_msg

    if _env_bool("STREAM_AUTO_RECORD", default=True) and not status["recording"]:
        await obs_controller._call("start_record")

    gameplay_scene = await _find_scene(
        "STREAM_GAMEPLAY_SCENE",
        "gameplay", "game", "main", "live", "content", "playing",
    )
    if gameplay_scene:
        await asyncio.sleep(1.5)
        await obs_controller._call("set_current_program_scene", gameplay_scene)
        return True, f"You're live, sir — switched to {gameplay_scene}. Good luck out there."

    return True, "You're live, sir. No gameplay scene configured, scene left as-is."


# ---------------------------------------------------------------------------
# Macro: brb_mode
# ---------------------------------------------------------------------------

async def brb_mode() -> tuple[bool, str]:
    """Switch to the BRB scene and optionally mute the mic.

    Returns (success, voice_message).
    """
    ok, err = await _ensure_obs_running()
    if not ok:
        return False, err

    brb_scene = await _find_scene(
        "STREAM_BRB_SCENE",
        "brb", "be right back", "away", "break", "pause",
    )
    if not brb_scene:
        return False, (
            "Couldn't find a BRB scene in OBS, sir. "
            "Create one named 'BRB' or set STREAM_BRB_SCENE in your .env."
        )

    result = await obs_controller._call("set_current_program_scene", brb_scene)
    if result is None:
        return False, f"Found the BRB scene but couldn't switch to it, sir."

    mic_note = ""
    if _env_bool("STREAM_BRB_MUTES_MIC", default=True):
        await _set_mic_muted(True)
        mic_note = " Mic muted."

    return True, f"BRB mode active, sir — switched to {brb_scene}.{mic_note}"


# ---------------------------------------------------------------------------
# Macro: panic_mode
# ---------------------------------------------------------------------------

async def panic_mode() -> tuple[bool, str]:
    """Emergency recovery — two modes controlled by STREAM_PANIC_STOPS_STREAM:

      false (default): Cut to safe scene + mute mic (stays live but hidden).
      true:            Stop stream and recording immediately.

    Returns (success, voice_message).
    """
    ok, err = await _ensure_obs_running()
    if not ok:
        return False, err

    if _env_bool("STREAM_PANIC_STOPS_STREAM", default=False):
        status = await obs_controller.get_status()
        if status and status["streaming"]:
            await obs_controller.stop_stream()
        if status and status["recording"]:
            await obs_controller._call("stop_record")
        return True, "Stream terminated, sir. You're offline."

    safe_scene = await _find_scene(
        "STREAM_SAFE_SCENE",
        "safe", "starting", "start", "waiting", "lobby", "brb", "break", "soon",
    )

    parts: list[str] = []
    if safe_scene:
        result = await obs_controller._call("set_current_program_scene", safe_scene)
        if result is not None:
            parts.append(f"cut to {safe_scene}")

    await _set_mic_muted(True)
    parts.append("mic muted")

    if parts:
        summary = " and ".join(parts)
        return True, f"Panic mode engaged, sir — {summary}. Take your time."

    return False, "Panic mode attempted but couldn't find a safe scene, sir."


# ---------------------------------------------------------------------------
# Macro: end_stream_safe
# ---------------------------------------------------------------------------

async def end_stream_safe() -> tuple[bool, str]:
    """Graceful stream wrap-up:
      1. Switch to the ending/outro scene.
      2. Brief pause so viewers see the outro.
      3. Stop the stream.
      4. Stop recording.

    Returns (success, voice_message).
    """
    ok, err = await _ensure_obs_running()
    if not ok:
        return False, err

    status = await obs_controller.get_status()
    if status is None:
        return False, "OBS doesn't appear to be running, sir."

    parts: list[str] = []

    ending_scene = await _find_scene(
        "STREAM_ENDING_SCENE",
        "ending", "end", "outro", "goodbye", "bye", "thanks", "thank you",
    )
    if ending_scene:
        result = await obs_controller._call("set_current_program_scene", ending_scene)
        if result is not None:
            parts.append(f"switched to {ending_scene}")
            await asyncio.sleep(2.0)

    if status["streaming"]:
        await obs_controller.stop_stream()
        parts.append("stream stopped")
    else:
        parts.append("stream was already offline")

    if status["recording"]:
        await obs_controller._call("stop_record")
        parts.append("recording saved")

    summary = ", ".join(parts) if parts else "all done"
    return True, f"Stream wrapped up, sir — {summary}. Good stream."
