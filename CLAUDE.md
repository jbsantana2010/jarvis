# JARVIS — Project Context for Claude

This file gives Claude full project context when starting a new session,
especially useful when switching between machines (home ↔ work laptop).

---

## What this project is

A voice-activated AI assistant running on WSL/Windows. The user speaks → browser
captures audio via Web Speech API → WebSocket → FastAPI backend → Anthropic Claude
for reasoning → Fish Audio for TTS → MP3 streamed back to browser. Falls back to
browser-native `window.speechSynthesis` if Fish Audio fails.

---

## Architecture

```
Browser (Vite + TypeScript)
  │  Web Speech API (STT)
  │  AudioContext (MP3 playback)
  │  window.speechSynthesis (TTS fallback)
  └─ WebSocket ──► FastAPI server (server.py)
                        │
                        ├─ Anthropic API (claude-haiku for classification,
                        │                 claude-sonnet for responses)
                        ├─ Fish Audio API (TTS → MP3 bytes → base64)
                        ├─ platform_adapter.py  (WSL/Windows OS ops)
                        ├─ actions.py           (high-level action helpers)
                        └─ conversation_db.py   (SQLite persistence)
```

---

## Key files

| File | Purpose |
|------|---------|
| `server.py` | Main FastAPI app, WebSocket handler, all action executors, system prompt |
| `platform_adapter.py` | All WSL/Windows OS calls (launch apps, open URLs, screenshot, clipboard) |
| `actions.py` | Higher-level helpers (open_app, open_browser, open_terminal) |
| `conversation_db.py` | SQLite conversation persistence (~/.jarvis/conversations.db) |
| `screen.py` | Screenshot routing (WSL → platform_adapter, macOS → native) |
| `frontend/src/main.ts` | WebSocket client, state machine, audio playback, browser TTS fallback |
| `frontend/src/voice.ts` | AudioContext queue player |
| `frontend/src/settings.ts` | Settings panel (preferences API) |

---

## Action tag system

The LLM embeds `[ACTION:TAG]` or `[ACTION:TAG:param]` tags in its response.
`server.py` strips them from spoken text and dispatches them as side effects.

Current actions: `OPEN_APP`, `BROWSE`, `SCREENSHOT`, `WEATHER`, `CALENDAR`,
`MAIL`, `READ_CLIPBOARD`, `WRITE_CLIPBOARD`, `WORK_MODE_START`, `WORK_MODE_STOP`

Fast-path: `detect_action_fast()` catches obvious commands via keyword match
before hitting the LLM (saves latency for things like "open calculator").

---

## Platform adapter — WSL specifics

- App launches: PowerShell `Start-Process` (primary), cmd `/c start` (fallback)
- URL opening: same `Start-Process` chain (avoids explorer.exe `?` wildcard bug)
- Screenshots: PowerShell `System.Drawing` → `$env:USERPROFILE\Pictures\Jarvis\`
- Clipboard read: `powershell.exe Get-Clipboard`
- Clipboard write: pipe to `clip.exe` stdin
- `_WIN_APP_REGISTRY`: maps friendly names → exe/URI (e.g. `discord` → `discord:`)

---

## Conversation persistence

`conversation_db.py` stores every turn in `~/.jarvis/conversations.db` (SQLite).
On WebSocket connect, the last 20 messages are loaded into `history[]` so the
assistant remembers context across server restarts. DB is pruned to 200 rows max.

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
DEV_MODE=1   # disables some guards during development
```

---

## Dev scripts

| Script | Purpose |
|--------|---------|
| `verify_jarvis.sh` | Full smoke test — run after a pull or before pushing |
| `typecheck_frontend.sh` | TypeScript type-check only |
| `setup_dev_env.sh` | First-time setup on a new machine (npm install + import check) |

---

## Sprint history (brief)

- **Sprint 1–2**: Core voice pipeline, Fish Audio TTS, basic action system
- **Sprint 3**: Windows app registry, WSL launch via PowerShell, weather, open_app
- **Sprint 4**: Screenshot (WSL), URI protocol launches (discord/spotify/calculator),
  work mode stop phrases, honest browser/calendar/mail stubs
- **Sprint 5**: Fixed browser search (explorer.exe `?` bug), frontend stuck-state fix,
  configurable screenshot path, normalize "open a tab and search" phrases
- **Sprint 6**: Browser TTS fallback (never silent), clipboard read/write,
  conversation persistence across restarts (SQLite)

---

## Common issues & fixes

**Search opens File Explorer**: `explorer.exe` treats `?` as a wildcard. Fixed by
using PowerShell `Start-Process` for all URL opening.

**Frontend stuck in speaking**: Server sends `status:idle` before audio finishes
playing. Fixed by ignoring server idle signals while `currentState === "speaking"`.

**TTS fallback stuck 30s**: `{type:"text"}` wasn't triggering audio, so state
never left speaking. Fixed by wiring text messages to `speakWithBrowserTts()`.

**Multi-line git commits in PowerShell**: heredoc syntax (`<<'EOF'`) is rejected.
Workaround: write commit message to `/tmp/` file, use `git commit -F`.
