# JARVIS — Project Context for Claude

This file gives Claude full project context when starting a new session,
especially useful when switching between machines (home ↔ work laptop).
**Always read this file first before making any changes.**

---

## What this project is

A voice-activated AI assistant running on WSL/Windows. The user speaks → browser
captures audio via Web Speech API → WebSocket → FastAPI backend → Anthropic Claude
for reasoning → Fish Audio for TTS → MP3 streamed back to browser. Falls back to
browser-native `window.speechSynthesis` if Fish Audio fails.

Current sprint: **Sprint 8 complete** (reminders + Windows notifications).

---

## Architecture

```
Browser (Vite + TypeScript)
  │  Web Speech API (STT)
  │  AudioContext (MP3 playback)
  │  window.speechSynthesis (TTS fallback)
  └─ WebSocket ──► FastAPI server (server.py)
                        │
                        ├─ Anthropic API (claude-haiku for fast responses,
                        │                 claude-sonnet for complex ones)
                        ├─ Fish Audio API (TTS → MP3 bytes → base64)
                        ├─ platform_adapter.py  (all WSL/Windows OS ops)
                        ├─ actions.py           (high-level action helpers)
                        ├─ mail_gmail.py        (Gmail read via OAuth)
                        ├─ conversation_db.py   (SQLite conversation history)
                        └─ reminders.py         (SQLite reminders + scheduler)
```

---

## Key files

| File | Purpose |
|------|---------|
| `server.py` | Main FastAPI app (~2700 lines), WebSocket handler, all action executors, system prompt, background scheduler |
| `platform_adapter.py` | All WSL/Windows OS calls: launch apps, open URLs, screenshot, clipboard, Windows notifications |
| `actions.py` | Higher-level helpers (open_app, open_browser, open_terminal) |
| `conversation_db.py` | SQLite conversation persistence (`~/.jarvis/conversations.db`) |
| `reminders.py` | SQLite reminder storage, natural language time parsing, voice formatting |
| `mail_gmail.py` | Gmail OAuth integration — read inbox, summarize with AI |
| `screen.py` | Screenshot routing (WSL → platform_adapter, macOS → native) |
| `dispatch_registry.py` | Tracks background Claude Code build tasks |
| `work_mode.py` | Work session management (claude -p subprocess) |
| `frontend/src/main.ts` | WebSocket client, state machine, audio playback, browser TTS fallback |
| `frontend/src/voice.ts` | AudioContext queue player |
| `frontend/src/settings.ts` | Settings panel (preferences API) |
| `verify_jarvis.sh` | Full smoke test — always run after a pull or before pushing |

---

## Action tag system

The LLM embeds `[ACTION:TAG] target` in its response. `server.py` strips the tag
from spoken text and dispatches the action as a background side effect.

**Current actions:**

| Action | What it does |
|--------|-------------|
| `OPEN_APP` | Launch a Windows app by name (registry-based) |
| `BROWSE` | Open URL or search query in default browser |
| `WEATHER` | Fetch weather for a city or saved default location |
| `SCREEN` | Capture and describe the screen |
| `READ_CLIPBOARD` | Read and speak clipboard contents |
| `WRITE_CLIPBOARD text` | Write text to clipboard |
| `READ_MAIL` | List recent Gmail messages |
| `SUMMARIZE_MAIL` | AI summary of Gmail inbox |
| `SET_REMINDER time \|\|\| message` | Create a timed reminder |
| `LIST_REMINDERS` | List all pending reminders |
| `ADD_TASK priority \|\|\| title \|\|\| desc \|\|\| date` | Create a task |
| `ADD_NOTE topic \|\|\| content` | Save a note |
| `COMPLETE_TASK id` | Mark a task done |
| `REMEMBER content` | Store a fact about the user |
| `PROMPT_PROJECT name \|\|\| prompt` | Dispatch to Claude Code in a project |
| `BUILD description` | Create and build a new project |
| `RESEARCH brief` | Web research + report document |
| `OPEN_TERMINAL` | Open Windows Terminal with Claude Code |

**Fast-path detection:** `detect_action_fast()` catches obvious commands via
keyword match before hitting the LLM (saves latency for "open calculator",
"what reminders do I have", clipboard ops, etc.).

---

## Platform adapter — WSL specifics

- App launches: PowerShell `Start-Process` (primary), cmd `/c start` (fallback)
- URL opening: same `Start-Process` chain (avoids explorer.exe `?` wildcard bug)
- Screenshots: PowerShell `System.Drawing` → `$env:USERPROFILE\Pictures\Jarvis\`
- Clipboard read: `powershell.exe Get-Clipboard`
- Clipboard write: pipe to `clip.exe` stdin
- Notifications: PowerShell `NotifyIcon` balloon — non-blocking, no installs needed
- `_WIN_APP_REGISTRY`: maps friendly names → exe/URI (e.g. `discord` → `discord:`)
- `notify_windows(title, message)`: fire-and-forget Windows balloon notification

---

## Reminder system (Sprint 8)

`reminders.py` manages time-based reminders in `~/.jarvis/reminders.db`.

**Time parsing supports:** `in 10 minutes`, `in 2 hours`, `at 6 PM`,
`at 3:30 PM`, `tomorrow at 9 AM`. Returns `None` if unparseable.

**Scheduler:** `_reminder_scheduler_loop()` runs as an `asyncio.create_task` at
server boot. Polls every 30 seconds. When a reminder fires:
1. Marks it `done` immediately (prevents double-firing).
2. Calls `platform_adapter.notify_windows()` — visible even if browser is closed.
3. Speaks via TTS on all active WebSocket connections.

**LLM action format:** `[ACTION:SET_REMINDER] in 10 minutes ||| stretch`
The `|||` separator splits time expression from message.

---

## Gmail integration (Sprint 7)

`mail_gmail.py` reads Gmail via OAuth. Credentials stored at
`~/.jarvis/gmail_token.json`. First run opens browser for OAuth consent.

Actions: `[ACTION:READ_MAIL]` lists recent messages, `[ACTION:SUMMARIZE_MAIL]`
uses Claude to summarize and highlight what matters.

---

## Conversation persistence

`conversation_db.py` stores every turn in `~/.jarvis/conversations.db` (SQLite).
On WebSocket connect, the last 20 messages are loaded into `history[]` so
JARVIS remembers context across server restarts. DB is pruned to 200 rows max.

---

## Work mode

"Start work mode" launches a `claude -p` subprocess (`WorkSession`). Subsequent
speech is routed there as a coding assistant. Stop phrases like "stop work mode",
"end work session", etc. return to normal voice mode.

---

## Frontend state machine

`idle → listening → thinking → speaking → idle`

- `status:idle` from server is **ignored** while in `speaking` state (prevents
  race where server finishes before audio playback completes).
- `speakingWatchdog`: 30s timeout forces idle if stuck in speaking state.
- `{type:"text"}` triggers browser TTS fallback (Fish Audio failure path).
- `{type:"audio"}` with valid base64 MP3 cancels browser TTS and plays Fish Audio.

---

## Environment variables (.env)

```
ANTHROPIC_API_KEY=
FISH_API_KEY=
FISH_VOICE_ID=612b878b113047d9a770c069c8b4fdfe
USER_LOCATION=San Juan, Puerto Rico
DEV_MODE=1
```

`DEV_MODE=1` disables SSL so the server runs plain HTTP (required for Vite proxy
in development). Do NOT set in production if you have certs.

---

## Dev scripts

| Script | Purpose |
|--------|---------|
| `verify_jarvis.sh` | Full smoke test — run after every pull or before pushing |
| `typecheck_frontend.sh` | TypeScript type-check only |
| `setup_dev_env.sh` | First-time setup on a new machine (npm install + import check) |

**Start JARVIS:**
```bash
# Terminal 1 — backend
cd ~/dev/jarvis/jarvis && DEV_MODE=1 python3 server.py

# Terminal 2 — frontend
cd ~/dev/jarvis/jarvis/frontend && npm run dev

# Browser
open http://localhost:5173
```

---

## Sprint history

| Sprint | What was built |
|--------|---------------|
| 1 | Platform adapter layer, WSL boot, DEV_MODE, graceful macOS stubs |
| 2 | Windows Terminal integration, browser control via Start-Process |
| 3 | Windows app registry (43 apps), PowerShell launch chain, weather |
| 4 | Screenshot (WSL), URI protocol launches, work mode stop phrases |
| 5 | Browser search fix (explorer.exe `?` bug), frontend stuck-state fix, settings |
| 6 | Browser TTS fallback, clipboard read/write, conversation persistence (SQLite) |
| 7 | Gmail integration (OAuth, read + AI summarize inbox) |
| 8 | Reminder system: SQLite storage, NL time parsing, background scheduler, Windows balloon notifications |

---

## Common issues & fixes

**Search opens File Explorer**: `explorer.exe` treats `?` as a wildcard. Fixed by
using PowerShell `Start-Process` for all URL opening.

**Frontend stuck in speaking**: Server sends `status:idle` before audio finishes
playing. Fixed by ignoring server idle signals while `currentState === "speaking"`.

**TTS fallback stuck 30s**: `{type:"text"}` wasn't triggering audio, so state
never left speaking. Fixed by wiring text messages to `speakWithBrowserTts()`.

**Multi-line git commits in PowerShell**: heredoc syntax (`<<'EOF'`) is rejected.
Workaround: write commit message to a temp file, use `git commit -F`.

**pip --break-system-packages**: WSL pip 22.x doesn't support this flag.
Use plain `pip3 install -r requirements.txt`.

**Vite proxy SSL error (EPROTO)**: Proxy target must be `http://` not `https://`
when backend runs with `DEV_MODE=1`. Already fixed in `vite.config.ts`.
