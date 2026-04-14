"""
JARVIS Platform Adapter -- centralized OS abstraction layer.

ALL platform-specific operations route through here.
Feature modules import from this file and never call OS tools directly.

Supported platforms:
  macos   -- full feature set (AppleScript, screencapture, open -a)
  wsl     -- core voice/LLM/memory; macOS features gracefully stubbed
  linux   -- same as wsl
  windows -- same as wsl (future: Win32 replacements go here)

Adding a Windows replacement:
  1. Add the implementation inside the relevant function under: if PLATFORM == "windows"
  2. Do NOT touch the calling module -- only this file changes.
"""

import asyncio
import platform
import logging
from pathlib import Path

log = logging.getLogger("jarvis.platform")

# ---------------------------------------------------------------------------
# Platform detection (runs once at import time)
# ---------------------------------------------------------------------------

def get_platform() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        try:
            with open("/proc/version") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except Exception:
            pass
        return "linux"
    return "unknown"


PLATFORM = get_platform()


def is_macos() -> bool:
    return PLATFORM == "macos"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_projects_path() -> Path:
    """Where JARVIS creates new projects.

    macOS      : ~/Desktop  (preserves original behaviour)
    WSL/Linux  : ~/jarvis-projects
    """
    if is_macos():
        return Path.home() / "Desktop"
    path = Path.home() / "jarvis-projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# AppleScript
# ---------------------------------------------------------------------------

_APPLESCRIPT_STUB = ("", "AppleScript is not available on this platform.", 1)


async def run_applescript(script: str, timeout: float = 10.0) -> tuple:
    """Run an AppleScript string.

    Returns (stdout: str, stderr: str, returncode: int).
    On non-macOS: returns a harmless stub -- callers already handle returncode != 0.
    """
    if not is_macos():
        return _APPLESCRIPT_STUB

    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(), stderr.decode(), proc.returncode
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "", "AppleScript timed out.", 124


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------

async def capture_screenshot(output_path: str, main_display_only: bool = True) -> bool:
    """Capture a screenshot to output_path.

    Returns True on success, False if unsupported or failed.
    """
    if not is_macos():
        return False

    cmd = ["screencapture", "-x"]
    if main_display_only:
        cmd.append("-m")
    cmd.append(output_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except asyncio.TimeoutError:
        return False


# ---------------------------------------------------------------------------
# Native app launcher
# ---------------------------------------------------------------------------

async def open_native_app(app_name: str) -> bool:
    """Launch a native GUI app in the background.

    macOS  : open -a <app_name> -g
    others : not yet implemented -- returns False
    """
    if not is_macos():
        return False

    proc = await asyncio.create_subprocess_exec(
        "open", "-a", app_name, "-g",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def log_platform_info():
    """Log platform summary at server startup."""
    log.info(f"Platform detected: {PLATFORM}")
    log.info(f"Projects path: {get_projects_path()}")
    if not is_macos():
        log.info("macOS features (calendar/mail/notes/screen/actions) are stubbed.")
        log.info("They return safe empty responses instead of crashing.")
