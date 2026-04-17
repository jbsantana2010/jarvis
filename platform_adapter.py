"""
JARVIS Platform Adapter -- centralized OS abstraction layer.

ALL platform-specific operations route through here.
Feature modules import from this file and never call OS tools directly.

Supported platforms:
  macos   -- full feature set (AppleScript, screencapture, open -a)
  wsl     -- core voice/LLM/memory; open_terminal + open_url via Windows interop
  linux   -- core voice/LLM/memory; open_terminal + open_url via xdg-open
  windows -- same as wsl (future: Win32 replacements go here)

Adding a Windows replacement:
  1. Add the implementation inside the relevant function under: if PLATFORM == "windows"
  2. Do NOT touch the calling module -- only this file changes.
"""

import asyncio
import base64
import os
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


async def take_screenshot_wsl() -> str | None:
    """Capture a screenshot on WSL/Windows via PowerShell + System.Drawing.

    Save location priority:
      1. SCREENSHOT_PATH env var  (full Windows path to a file, e.g. C:\\Users\\you\\ss.png)
      2. %USERPROFILE%\\Pictures\\Jarvis\\jarvis_screenshot.png  (auto-created)

    The PowerShell script writes the actual save path to stdout so we can
    locate the file from WSL regardless of username.

    Returns base64-encoded PNG string, or None on failure.
    """
    custom_path = os.environ.get("SCREENSHOT_PATH", "").strip()
    if custom_path:
        # User supplied a specific Windows path
        ps_path_block = f"$outFile = '{custom_path.replace(chr(39), '')}'"
        ps_mkdir_block = "$outDir = Split-Path -Parent $outFile; if (-not (Test-Path $outDir)) {{ New-Item -ItemType Directory -Path $outDir | Out-Null }}"
    else:
        ps_path_block = (
            "$outDir = [System.IO.Path]::Combine($env:USERPROFILE, 'Pictures', 'Jarvis'); "
            "if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }; "
            "$outFile = [System.IO.Path]::Combine($outDir, 'jarvis_screenshot.png')"
        )
        ps_mkdir_block = ""

    ps_script = (
        f"{ps_path_block}; "
        + (f"{ps_mkdir_block}; " if ps_mkdir_block else "")
        + "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$s = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
        "$bmp = New-Object System.Drawing.Bitmap($s.Width, $s.Height); "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($s.Location, [System.Drawing.Point]::Empty, $s.Size); "
        "$bmp.Save($outFile); "
        "$g.Dispose(); $bmp.Dispose(); "
        "Write-Output $outFile"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-Command", ps_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            log.warning("take_screenshot_wsl: PowerShell timed out")
            return None

        err = stderr.decode().strip() if stderr else ""
        if err and any(k in err.lower() for k in ("error", "exception", "cannot")):
            log.warning(f"take_screenshot_wsl PowerShell error: {err[:200]}")
            return None

        # PowerShell writes the Windows save path to stdout
        win_path = stdout.decode().strip() if stdout else ""
        if not win_path:
            log.warning("take_screenshot_wsl: PowerShell produced no output path")
            return None

        # Convert Windows path → WSL mount path
        # e.g. C:\Users\jb\Pictures\Jarvis\... → /mnt/c/Users/jb/Pictures/Jarvis/...
        wsl_path_str = "/mnt/" + win_path[0].lower() + win_path[2:].replace("\\", "/")
        wsl_path = Path(wsl_path_str)

        if not wsl_path.exists():
            log.warning(f"take_screenshot_wsl: file not found at WSL path {wsl_path_str}")
            return None

        data = wsl_path.read_bytes()
        log.info(f"WSL screenshot: {len(data)} bytes saved to {wsl_path_str}")
        return base64.b64encode(data).decode()

    except Exception as e:
        log.error(f"take_screenshot_wsl failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Clipboard  (WSL / Windows)
# ---------------------------------------------------------------------------

async def read_clipboard_wsl() -> str:
    """Read text content from the Windows clipboard via PowerShell Get-Clipboard.

    Returns the clipboard text, or an empty string on failure / empty clipboard.
    """
    if PLATFORM not in ("wsl", "windows"):
        return ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-Command", "Get-Clipboard",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout.decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        log.warning("read_clipboard_wsl: timed out")
        return ""
    except Exception as e:
        log.error(f"read_clipboard_wsl failed: {e}")
        return ""


async def write_clipboard_wsl(text: str) -> bool:
    """Write text to the Windows clipboard using clip.exe (reads from stdin).

    clip.exe is always available on Windows and avoids PowerShell quoting issues.
    Returns True on success.
    """
    if PLATFORM not in ("wsl", "windows"):
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "clip.exe",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(
            proc.communicate(input=text.encode("utf-8")),
            timeout=5,
        )
        err = stderr.decode().strip() if stderr else ""
        if err:
            log.warning(f"write_clipboard_wsl clip.exe warning: {err[:120]}")
        log.info(f"Clipboard written: {len(text)} chars")
        return True
    except asyncio.TimeoutError:
        log.warning("write_clipboard_wsl: timed out")
        return False
    except Exception as e:
        log.error(f"write_clipboard_wsl failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Native app launcher (macOS only)
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
# Terminal launcher  (Sprint 2 — WSL/Windows)
# ---------------------------------------------------------------------------

async def open_terminal(command: str = "") -> bool:
    """Open a terminal window, optionally running a command.

    macOS  : Handled in actions.py via AppleScript (not called here).
    WSL    : Opens Windows Terminal (wt.exe), fallback to cmd.exe.
    Linux  : Tries gnome-terminal, then xterm.
    """
    if PLATFORM in ("wsl", "windows"):
        return await _open_terminal_windows(command)
    if PLATFORM == "linux":
        return await _open_terminal_linux(command)
    return False


async def _open_terminal_windows(command: str = "") -> bool:
    """Open Windows Terminal (wt.exe) from WSL, falling back to cmd.exe."""
    # --- primary: Windows Terminal ---
    try:
        if command:
            cmd = ["wt.exe", "wsl.exe", "--", "bash", "-i", "-c", command]
        else:
            cmd = ["wt.exe"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # wt.exe detaches immediately — wait briefly then treat as success
        try:
            await asyncio.wait_for(proc.communicate(), timeout=3)
        except asyncio.TimeoutError:
            pass
        log.info("Opened Windows Terminal via wt.exe")
        return True
    except FileNotFoundError:
        log.warning("wt.exe not found — falling back to cmd.exe")
    except Exception as e:
        log.warning(f"wt.exe failed ({e}) — falling back to cmd.exe")

    # --- fallback: cmd.exe ---
    try:
        if command:
            proc = await asyncio.create_subprocess_exec(
                "cmd.exe", "/c", "start", "cmd.exe", "/k",
                f"wsl.exe bash -i -c \"{command}\"",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                "cmd.exe", "/c", "start", "cmd.exe",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=3)
        except asyncio.TimeoutError:
            pass
        log.info("Opened terminal via cmd.exe fallback")
        return True
    except Exception as e:
        log.error(f"cmd.exe terminal fallback also failed: {e}")
        return False


async def _open_terminal_linux(command: str = "") -> bool:
    """Open a terminal on native Linux (non-WSL)."""
    for term in ["gnome-terminal", "xfce4-terminal", "konsole", "xterm"]:
        try:
            if command and term == "gnome-terminal":
                args = [term, "--", "bash", "-c", command]
            elif command:
                args = [term, "-e", f"bash -c '{command}'"]
            else:
                args = [term]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=3)
            except asyncio.TimeoutError:
                pass
            log.info(f"Opened terminal via {term}")
            return True
        except FileNotFoundError:
            continue
        except Exception as e:
            log.warning(f"{term} failed: {e}")
            continue
    log.error("No terminal emulator found on Linux")
    return False


# ---------------------------------------------------------------------------
# URL / Browser launcher  (Sprint 2 — WSL/Windows)
# ---------------------------------------------------------------------------

async def open_url(url: str) -> bool:
    """Open a URL in the system default browser.

    macOS  : Handled in actions.py via AppleScript (not called here).
    WSL    : explorer.exe <url>, fallback to cmd.exe /c start.
    Linux  : xdg-open <url>.
    """
    if PLATFORM in ("wsl", "windows"):
        return await _open_url_windows(url)
    if PLATFORM == "linux":
        return await _open_url_linux(url)
    return False


async def _open_url_windows(url: str) -> bool:
    """Open a URL via Windows browser interop from WSL.

    Uses PowerShell Start-Process as the primary method — it correctly hands
    URLs to the registered default browser without the wildcard-path ambiguity
    that plagues explorer.exe when the URL contains '?' or '&'.
    Falls back to cmd.exe /c start, then explorer.exe.
    """
    # Escape single-quotes for PowerShell string literal
    safe_url = url.replace("'", "%27")

    # --- primary: PowerShell Start-Process ---
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-Command",
            f"Start-Process '{safe_url}'",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
            err = (stderr or b"").decode().strip()
        except asyncio.TimeoutError:
            err = ""  # PowerShell detached — fine
        failed_kw = ("not recognized", "not found", "cannot find", "access is denied")
        if err and any(k in err.lower() for k in failed_kw):
            log.warning(f"PowerShell URL failed: {err[:120]}")
            raise RuntimeError(err)
        log.info(f"Opened URL via PowerShell Start-Process: {url}")
        return True
    except Exception as e:
        log.warning(f"PowerShell Start-Process URL failed ({e}) — trying cmd.exe start")

    # --- fallback 1: cmd.exe /c start ---
    try:
        # cmd start needs the URL in double-quotes; & must not be unescaped
        proc = await asyncio.create_subprocess_exec(
            "cmd.exe", "/c", "start", '""', url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            pass
        log.info(f"Opened URL via cmd.exe start: {url}")
        return True
    except Exception as e:
        log.warning(f"cmd.exe start URL failed ({e}) — trying explorer.exe")

    # --- fallback 2: explorer.exe (last resort, may open file explorer on some URLs) ---
    try:
        proc = await asyncio.create_subprocess_exec(
            "explorer.exe", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            pass
        log.info(f"Opened URL via explorer.exe: {url}")
        return True
    except Exception as e:
        log.error(f"All URL-open methods failed: {e}")
        return False


async def _open_url_linux(url: str) -> bool:
    """Open a URL on native Linux via xdg-open."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdg-open", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            pass
        log.info(f"Opened URL via xdg-open: {url}")
        return True
    except Exception as e:
        log.error(f"xdg-open failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def log_platform_info():
    """Log platform summary at server startup."""
    log.info(f"Platform detected: {PLATFORM}")
    log.info(f"Projects path: {get_projects_path()}")
    if not is_macos():
        log.info("macOS features (calendar/mail/notes/screen/AppleScript) are stubbed.")
        log.info("WSL features active: open_terminal (wt.exe), open_url (explorer.exe).")

# ---------------------------------------------------------------------------
# Windows App Registry  (Sprint 3)
# ---------------------------------------------------------------------------
# Maps lowercase human names / aliases → Windows executable or URI.
# Add new apps here — nowhere else needs to change.

_WIN_APP_REGISTRY: dict[str, str] = {
    # Browsers
    "chrome":               "chrome.exe",
    "google chrome":        "chrome.exe",
    "edge":                 "msedge.exe",
    "microsoft edge":       "msedge.exe",
    "firefox":              "firefox.exe",
    # Editors / IDEs
    "vscode":               "code",
    "vs code":              "code",
    "visual studio code":   "code",
    "notepad":              "notepad.exe",
    "notepad++":            "notepad++.exe",
    # System utilities — Calculator is UWP on Win10/11, use URI
    "calculator":           "ms-calculator:",
    "calc":                 "ms-calculator:",
    "file explorer":        "explorer.exe",
    "explorer":             "explorer.exe",
    "files":                "explorer.exe",
    "task manager":         "taskmgr.exe",
    "taskmgr":              "taskmgr.exe",
    "control panel":        "control.exe",
    "paint":                "mspaint.exe",
    "mspaint":              "mspaint.exe",
    "snipping tool":        "snippingtool.exe",
    "snip":                 "snippingtool.exe",
    # Terminals / shells
    "terminal":             "wt.exe",
    "windows terminal":     "wt.exe",
    "cmd":                  "cmd.exe",
    "command prompt":       "cmd.exe",
    "powershell":           "powershell.exe",
    # Windows URI launchers (no .exe needed)
    "settings":             "ms-settings:",
    "windows settings":     "ms-settings:",
    "clock":                "ms-clock:",
    "weather app":          "ms-weather:",
    # Communication — these apps use URI protocols (not in PATH)
    "discord":              "discord:",       # registered URI handler
    "slack":                "slack:",
    "teams":                "msteams:",
    "microsoft teams":      "msteams:",
    "zoom":                 "zoommtg:",
    "telegram":             "tg:",
    # Media
    "spotify":              "spotify:",       # registered URI handler
    "vlc":                  "vlc.exe",        # usually in PATH
    # Office
    "word":                 "winword.exe",
    "excel":                "excel.exe",
    "powerpoint":           "powerpnt.exe",
    "outlook":              "outlook.exe",
    # Streaming / recording — full path since OBS isn't in Windows PATH
    "obs":                  r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "obs studio":           r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    "open broadcaster":     r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
}


async def open_windows_app(app_name: str) -> tuple[bool, str]:
    """Open a Windows app by human name from WSL.

    Returns (success, message).
    Tries exact match → substring match → direct launch as last resort.
    """
    if PLATFORM not in ("wsl", "windows"):
        return False, f"App launching is only supported on Windows/WSL (current: {PLATFORM})."

    key = app_name.lower().strip()

    # 1. Exact match
    executable = _WIN_APP_REGISTRY.get(key)

    # 2. Substring match (e.g. "chrome" matches "google chrome")
    if not executable:
        for reg_key, reg_exe in _WIN_APP_REGISTRY.items():
            if key in reg_key or reg_key in key:
                executable = reg_exe
                log.info(f"App fuzzy-matched '{key}' → '{reg_key}' ({reg_exe})")
                break

    # 3. Try launching the raw name directly (user might know the exact exe)
    if not executable:
        log.warning(f"'{app_name}' not in registry — attempting direct launch")
        executable = app_name

    return await _launch_windows_app(executable, app_name)


async def _launch_windows_app(executable: str, display_name: str) -> tuple[bool, str]:
    """Launch a Windows exe or URI from WSL via PowerShell Start-Process."""
    try:
        if executable.endswith(":"):
            # Windows URI protocol (ms-settings:, ms-clock:, ...)
            cmd = ["powershell.exe", "-NoProfile", "-Command",
                   f"Start-Process '{executable}'"]
        else:
            # For full-path exes, set WorkingDirectory to the exe's own folder
            # so apps like OBS can find their locale/data files relative to themselves
            win_dir = executable.replace("/", "\\").rsplit("\\", 1)[0] if "\\" in executable else ""
            if win_dir:
                cmd = ["powershell.exe", "-NoProfile", "-Command",
                       f"Start-Process '{executable}' -WorkingDirectory '{win_dir}'"]
            else:
                cmd = ["powershell.exe", "-NoProfile", "-Command",
                       f"Start-Process '{executable}'"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
            err = stderr.decode().strip() if stderr else ""
        except asyncio.TimeoutError:
            err = ""  # PowerShell detaches and times out — that's fine

        # PowerShell exit code 1 often means "app launched but PS exited"
        # Only treat it as failure if stderr contains "not recognized" or "not found"
        failed_keywords = ("not recognized", "not found", "cannot find",
                           "no such file", "access is denied")
        if err and any(k in err.lower() for k in failed_keywords):
            log.error(f"App launch failed for '{executable}': {err[:120]}")
            return False, f"Couldn't find {display_name} on this machine, sir."

        log.info(f"Launched Windows app: {executable}")
        return True, f"{display_name.title()} is open, sir."

    except Exception as e:
        log.error(f"_launch_windows_app failed for '{executable}': {e}")
        return False, f"Had trouble opening {display_name}, sir."


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

async def _wait_and_forget(proc) -> None:
    """Silently wait for a fire-and-forget background subprocess."""
    try:
        await asyncio.wait_for(proc.communicate(), timeout=15)
    except Exception:
        pass


async def notify_windows(title: str, message: str) -> bool:
    """Show a desktop notification.

    macOS  : AppleScript display notification
    WSL    : PowerShell NotifyIcon balloon — visible even when browser is
             closed; no extra installs required on Windows 10/11.

    Returns True if the notification was dispatched successfully.
    """
    if is_macos():
        safe_msg   = message.replace('"', '\\"')
        safe_title = title.replace('"', '\\"')
        script = f'display notification "{safe_msg}" with title "{safe_title}"'
        _, _, rc = await run_applescript(script)
        return rc == 0

    # WSL / Windows — PowerShell balloon notification
    safe_msg   = message.replace("'", "''")
    safe_title = title.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f"$n.BalloonTipTitle = '{safe_title}'; "
        f"$n.BalloonTipText = '{safe_msg}'; "
        "$n.BalloonTipIcon = 'Info'; "
        "$n.ShowBalloonTip(8000); "
        "Start-Sleep 9; "
        "$n.Dispose()"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-WindowStyle", "Hidden", "-NonInteractive",
            "-Command", ps,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        asyncio.create_task(_wait_and_forget(proc))
        return True
    except Exception as e:
        log.warning(f"notify_windows failed: {e}")
        return False
