# JARVIS — Project Context for Claude

This file gives Claude full project context when starting a new session,
especially useful when switching between machines (home ↔ work laptop).
**Always read this file first before making any changes.**

---

## What this project is

A voice-activated AI assistant running on WSL/Windows. The user speaks → audio
captured via server-side faster-whisper ASR (Sprint 18) or browser Web Speech API
fallback → WebSocket → FastAPI backend → Anthropic Claude for reasoning → Fish Audio
for TTS → MP3 streamed back to browser. Falls back to browser-native
window.speechSynthesis if Fish Audio fails.

Current sprint: **Sprint 18 complete** (Server-side Whisper ASR).

---

## Architecture

Browser (Vite + TypeScript)
  whisperVoice.ts — MediaRecorder + VAD → POST /api/stt/transcribe (Sprint 18)
  voice.ts        — Web Speech API fallback (auto-selected if Whisper unavailable)
  AudioContext (MP3 playback)
  window.speechSynthesis (TTS fallback)
  contextMode.ts  — UI mode machine: ambient / dashboard / context (Sprint 16)
  WebSocket → FastAPI server (server.py)
                        |
                        +- Anthropic API (claude-haiku fast, claude-sonnet complex)
                        +- Fish Audio API (TTS -> MP3 bytes -> base64)
                        +- whisper_stt.py        (faster-whisper ASR, Sprint 18)
                        +- platform_adapter.py   (all WSL/Windows OS ops)
                        +- actions.py            (high-level action helpers)
                        +- mail_gmail.py         (Gmail read via OAuth)
                        +- calendar_google.py    (Google Calendar read+write via OAuth)
                        +- briefing.py           (morning briefing + daily overview)
                        +- search_web.py         (Brave Search API + freshness)
                        +- obs_controller.py     (OBS Studio via WebSocket v5)
                        +- stream_copilot.py     (multi-step OBS macro sequences)
                        +- spotify_controller.py (Spotify Web API via spotipy)
                        +- budget_reader.py      (local Excel budget parsing)
                        +- budget_analyzer.py    (debt totals, payoff strategy)
                        +- project_manager.py    (SQLite project + blocker tracking)
                        +- conversation_db.py    (SQLite conversation history)
                        +- reminders.py          (SQLite reminders + scheduler)

---

## Key files

| File | Purpose |
|------|---------|
| server.py | Main FastAPI app, WebSocket handler, all action executors, system prompt, scheduler |
| whisper_stt.py | faster-whisper wrapper: preload(), transcribe_bytes(), transcribe_async() |
| platform_adapter.py | All WSL/Windows OS calls: launch apps, open URLs, screenshot, clipboard, notifications |
| actions.py | Higher-level helpers (open_app, open_browser, open_terminal) |
| conversation_db.py | SQLite conversation persistence (~/.jarvis/conversations.db) |
| reminders.py | SQLite reminder storage, natural language time parsing, voice formatting |
| mail_gmail.py | Gmail OAuth integration -- read inbox, summarize with AI |
| calendar_google.py | Google Calendar OAuth -- read events + create new events (full scope) |
| briefing.py | Morning briefing: weather + calendar + unread mail summary |
| search_web.py | Brave Search API with freshness param for live data (prices, scores, news) |
| obs_controller.py | OBS Studio WebSocket v5 control (scenes, streaming, recording, mic) |
| stream_copilot.py | High-level OBS macros: stream_prep, go_live, brb_mode, panic_mode, end_stream |
| spotify_controller.py | Spotify Web API via spotipy: play/pause/skip/volume/search/queue |
| budget_reader.py | Loads Juan_Financial_Dashboard.xlsx; parses Debts, Snapshot, Calendar sheets |
| budget_analyzer.py | Debt totals, avalanche/snowball payoff strategy, voice-friendly output |
| project_manager.py | SQLite project tracking: add, log, blockers, standup, focus, weekly digest |
| screen.py | Screenshot routing (WSL -> platform_adapter, macOS -> native) |
| dispatch_registry.py | Tracks background Claude Code build tasks |
| work_mode.py | Work session management (claude -p subprocess) |
| frontend/src/main.ts | WebSocket client, state machine, audio playback, Whisper/browser STT auto-select |
| frontend/src/voice.ts | Web Speech API voice input + AudioContext queue player |
| frontend/src/whisperVoice.ts | Whisper voice input: MediaRecorder + VAD + HTTP POST (Sprint 18) |
| frontend/src/contextMode.ts | UI mode state machine: ambient/dashboard/context, 15s auto-dismiss |
| frontend/src/components/CalendarWidget.ts | Calendar widget polling /api/dashboard/calendar |
| frontend/src/settings.ts | Settings panel (preferences API) |
| verify_jarvis.sh | Full smoke test -- always run after a pull or before pushing |

---

## Whisper ASR (Sprint 18)

### Backend — whisper_stt.py
Uses faster-whisper (CTranslate2-based, runs on CPU).

```python
MODEL_SIZE = os.getenv("WHISPER_MODEL", "tiny")   # tiny/base/small/medium
preload()           # eager model load at server startup (called from lifespan)
is_available()      # returns True if model loaded successfully
transcribe_bytes(audio_bytes, suffix=".webm") -> str
transcribe_async(audio_bytes, suffix=".webm") -> str  # executor wrapper
```

Options in transcribe_bytes(): beam_size=1, vad_filter=True, language="en"

### Server endpoints
- GET /api/stt/status → `{"available": true, "model": "tiny"}`
- POST /api/stt/transcribe → multipart `audio` field → `{"text": "..."}`

### Frontend — whisperVoice.ts
- getUserMedia() once, reuses stream
- AudioContext AnalyserNode polls every 40ms for RMS energy
- RMS > 0.012 → speech start, MediaRecorder.start()
- Silence > 700ms → stop recording → POST blob to /api/stt/transcribe
- Min utterance: 200ms / Min blob: 1KB (noise rejection)
- MIME preference: webm;codecs=opus → webm → ogg → mp4
- Implements same VoiceInput interface as voice.ts (start/stop/pause/resume)

### Auto-selection in main.ts
activate() calls buildVoiceInput() which:
1. Fetches /api/stt/status — if available: true → uses whisperVoice.ts
2. On any error or available: false → falls back to browser Web Speech API

### Install
```bash
pip3 install faster-whisper
```
Model downloads automatically on first preload() call (~75 MB for tiny).

---

## Action tag system

The LLM embeds [ACTION:TAG] target in its response. server.py strips the tag
from spoken text and dispatches the action as a background side effect.

Three dispatch paths:
1. detect_action_fast() -- keyword-matched shortcut before LLM (low latency)
2. Work mode -- routes to claude -p subprocess
3. Regex scan of LLM response for embedded [ACTION:TAG] tokens

### All current actions

| Action | What it does |
|--------|-------------|
| OPEN_APP | Launch a Windows app by name (registry-based) |
| BROWSE | Open URL or search query in default browser |
| WEATHER | Fetch weather for a city or saved default location |
| SCREEN | Capture and describe the screen |
| READ_CLIPBOARD | Read and speak clipboard contents |
| WRITE_CLIPBOARD text | Write text to clipboard |
| READ_MAIL | List recent Gmail messages |
| SUMMARIZE_MAIL | AI summary of Gmail inbox |
| SET_REMINDER time ||| message | Create a timed reminder |
| LIST_REMINDERS | List all pending reminders |
| ADD_TASK priority ||| title ||| desc ||| date | Create a task |
| ADD_NOTE topic ||| content | Save a note |
| COMPLETE_TASK id | Mark a task done |
| REMEMBER content | Store a fact about the user |
| PROMPT_PROJECT name ||| prompt | Dispatch to Claude Code in a project |
| BUILD description | Create and build a new project |
| RESEARCH brief | Web research + report document |
| OPEN_TERMINAL | Open Windows Terminal with Claude Code |
| READ_CALENDAR | List upcoming Google Calendar events |
| NEXT_EVENT | Speak the very next calendar event |
| MORNING_BRIEFING | Full briefing: weather + calendar + email |
| WHATS_NEXT | Next 3 calendar events |
| DAILY_OVERVIEW | Today's full calendar schedule |
| WEB_SEARCH query | Search via Brave API (freshness for live data) |
| OBS_STATUS | Check OBS WebSocket connection |
| START_STREAM | Start OBS streaming |
| STOP_STREAM | Stop OBS streaming |
| START_RECORDING | Start OBS recording |
| STOP_RECORDING | Stop OBS recording |
| SWITCH_SCENE scene_name | Switch OBS to named scene |
| LIST_SCENES | List all OBS scenes |
| TOGGLE_MIC | Toggle microphone mute in OBS |
| STREAM_PREP | Macro: starting scene + unmute mic + start recording |
| GO_LIVE | Macro: start stream + recording + switch to gameplay scene |
| BRB_MODE | Macro: BRB scene + mute mic |
| PANIC_MODE | Macro: safe scene + mute (hard mode also stops stream) |
| END_STREAM | Macro: ending scene + 2s pause + stop stream + stop recording |
| CREATE_CALENDAR_EVENT title ||| start_iso ||| end_iso | Create calendar event |
| SPOTIFY_STATUS | Show what's currently playing on Spotify |
| SPOTIFY_PLAY | Resume Spotify playback |
| SPOTIFY_PAUSE | Pause Spotify |
| SPOTIFY_SKIP | Skip to next track |
| SPOTIFY_PREVIOUS | Go back to previous track |
| SPOTIFY_VOLUME amount | Set Spotify volume (0-100) |
| SPOTIFY_PLAY_QUERY query | Search and play artist/playlist/track |
| SPOTIFY_QUEUE query | Add a track to the queue |
| BUDGET_SUMMARY | Income, outflow, deficit, total debt, interest burned, DTI |
| BUDGET_TOTAL_DEBT | Total with top-3 by balance + min payment total |
| BUDGET_SHOW_DEBTS | All debts: name, balance, APR, minimum, status |
| BUDGET_PAYOFF_PLAN | Avalanche (or snowball if no APR), top-5 targets |
| BUDGET_HIGHEST_INTEREST | Highest APR debt, balance, monthly cost |
| BUDGET_MONTHLY_DUE | Total minimums grouped by early/mid/late month |
| PROJECT_ADD | Register new project |
| PROJECT_STATUS | Full status: priority, last update, blockers |
| PROJECT_LOG | Append timestamped update |
| PROJECT_BLOCKER | Add open blocker |
| PROJECT_RESOLVE_BLOCKER | Mark best-matching blocker resolved |
| PROJECT_SET_STATUS | Change project status (done/paused/active) |
| PROJECT_STANDUP | All active projects: last update + blockers |
| PROJECT_FOCUS | AI recommendation of what to work on next |
| PROJECT_WEEKLY | All updates logged in the past 7 days |
| PROJECT_UNTOUCHED | Active projects not touched in last 5 days |

**Fast-path safety rules (critical):**
- STOP_STREAM and STOP_RECORDING: phrase must LEAD the sentence (no substring match)
- SWITCH_SCENE: filters pronoun-only targets (it, that, this, there, etc.)

---

## Contextual UI System (Sprints 15–16)

Three UI modes controlled by body class:
- `mode-ambient` — orb only + pill indicator (default after activation)
- `mode-dashboard` — full layout with all widgets visible
- `mode-context` — floating panel triggered by voice keywords

Voice triggers (contextMode.ts detectPanelTrigger):
- "go live" / "start stream" / "obs" → OBS panel
- "what's playing" / "spotify" / "skip track" → Spotify panel
- "my debt" / "budget" / "my balance" → Budget panel
- "work on" / "my projects" / "what should" → Projects panel
- "check email" / "my email" / "inbox" → Email panel

Auto-dismiss: 15s countdown bar (requestAnimationFrame). Click orb pill → dashboard.

Dashboard widgets:
- JarvisBrain (orb + voice state)
- Calendar widget (polls /api/dashboard/calendar every 5 min)
- Spotify widget
- OBS widget
- Projects widget

---

## Orb visualization (Sprints 15, 17)

frontend/src/orb.ts — Three.js WebGL particle orb with CSS fallback.

WebGL: alpha:true + setClearColor(0,0) for transparent canvas.
Canvas constrained to 420px in dashboard mode (body.mode-dashboard #orb-canvas).
Resize handler uses canvas.clientWidth/Height (not window size).

States → colors:
- idle     → dim blue  (#3a6a9a)
- listening → bright blue (#4db8ff)
- thinking  → purple (#a855f7)
- speaking  → green (#22c55e)

setState() adds body.orb-[state] class for CSS glow effects.
CSS fallback: #orb-fallback div with radial gradient, activated if WebGL throws.

---

## Platform adapter — WSL specifics

- App launches: PowerShell Start-Process (primary), cmd /c start (fallback)
- URL opening: same Start-Process chain (avoids explorer.exe ? wildcard bug)
- Screenshots: PowerShell System.Drawing -> USERPROFILE\Pictures\Jarvis\
- Clipboard read: powershell.exe Get-Clipboard
- Clipboard write: pipe to clip.exe stdin
- Notifications: PowerShell NotifyIcon balloon -- non-blocking, no installs needed
- _WIN_APP_REGISTRY: maps friendly names -> exe/URI (e.g. discord -> discord:)
- notify_windows(title, message): fire-and-forget Windows balloon notification

---

## WSL2 Networking (critical -- read before touching OBS or OAuth)

WSL2 is a VM with NAT networking. The Windows host IP is NOT localhost from WSL.

**Correct way to find Windows host IP:**
  ip route | awk '/^default/ {print $3; exit}'
  Typically: 172.27.32.1 (changes on reboot but gateway is always correct)
  Do NOT use /etc/resolv.conf nameserver -- that is the DNS resolver, not the host.

**OBS WebSocket (obs_controller.py):**
  _get_windows_host_ip() tries default gateway first, falls back to resolv.conf nameserver.
  OBS must have WebSocket server enabled (Tools > WebSocket Server Settings, port 4455).
  Windows Firewall MUST have an inbound rule for TCP 4455 from WSL subnet.
  To add the rule (run as Admin in PowerShell on Windows):
    New-NetFirewallRule -DisplayName "OBS WebSocket WSL" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Allow

**OAuth callback servers (Gmail, Calendar, Spotify):**
  All OAuth redirect servers bind to 0.0.0.0 so the Windows browser can reach them.
  After capturing the auth code, swap the redirect URL host back to 127.0.0.1
  for the token exchange (Google/Spotify reject the WSL IP as an authorized redirect).
  Also requires: export OAUTHLIB_INSECURE_TRANSPORT=1 (plain HTTP in dev mode).

---

## Google Calendar integration

calendar_google.py reads and writes Google Calendar via OAuth.
Token cached at token_calendar.json in project root.
Scope: https://www.googleapis.com/auth/calendar (full read+write).

If you see 403 accessNotConfigured: enable Google Calendar API in GCloud console.
If scope changes (e.g. adding write): delete token_calendar.json to force re-auth.

create_event(title, start_iso, end_iso, description="") -> tuple[bool, str]
  Uses service.events().insert(calendarId="primary", body=body).execute()

LLM format: [ACTION:CREATE_CALENDAR_EVENT] Meeting with Bob ||| 2025-01-15T14:00:00 ||| 2025-01-15T15:00:00
  server.py parses the ||| separators; end defaults to 1 hour after start if omitted.

---

## Morning Briefing (Sprint 9)

briefing.py composes a spoken briefing from three sources:
  1. Weather (platform_adapter weather fetch)
  2. Google Calendar events for today
  3. Unread Gmail count / recent subject lines

Actions: MORNING_BRIEFING, DAILY_OVERVIEW, WHATS_NEXT
Fast-path triggers: "good morning", "morning briefing", "what is my day", "daily overview"

---

## Web Search (Sprint 10)

search_web.py uses Brave Search API (BRAVE_SEARCH_API_KEY in .env).
Returns top 7 results; Haiku summarizes them into a spoken answer.

Freshness: _needs_freshness(query) checks for keywords like "today", "now",
"price", "score", "weather", "latest", "current". If matched, adds freshness="pw"
(past week) to the Brave API call to prioritize recent content.

---

## OBS Studio integration (Sprint 10)

obs_controller.py controls OBS via obsws_python (WebSocket protocol v5).
Connection to Windows host at gateway IP (see WSL2 Networking above), port 4455.

Key functions:
  get_status() -> dict with streaming/recording state
  start_stream(), stop_stream(), start_recording(), stop_recording()
  switch_scene(name), list_scenes() -> list[str]
  get_input_mute(input_name), set_input_mute(input_name, muted)
  toggle_mic() -- toggles the input named in OBS_MIC_INPUT_NAME env var

Env vars: OBS_HOST (auto-detected), OBS_PORT (4455), OBS_PASSWORD, OBS_MIC_INPUT_NAME

---

## Stream Copilot (Sprint 11)

stream_copilot.py contains five async macro functions:
  stream_prep(), go_live(), brb_mode(), panic_mode(), end_stream_safe()

_find_scene(env_key, *keywords): checks env var first, falls back to keyword scan.
_set_mic_muted(muted): explicit state (not toggle).

Env vars for scene names:
  STREAM_STARTING_SCENE, STREAM_GAMEPLAY_SCENE, STREAM_BRB_SCENE,
  STREAM_SAFE_SCENE, STREAM_ENDING_SCENE
  STREAM_BRB_MUTES_MIC=true, STREAM_PANIC_STOPS_STREAM=false

---

## Spotify Control (Sprint 12)

spotify_controller.py uses spotipy + Spotify Web API. OAuth cached at token_spotify.json.
Required env vars: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
Requires Spotify Premium for playback control.

---

## Budget Assistant (Sprint 13)

Reads Juan_Financial_Dashboard.xlsx from a local OneDrive folder.
Files: budget_reader.py (openpyxl parser), budget_analyzer.py (calculations).
Budget file: /mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/Payoff debts/
Override location: BUDGET_FOLDER in .env
Sheets used: Debts (11 debts, APR, balance, min), Snapshot (income/expenses), Calendar (due dates).

---

## Project Management (Sprint 14)

project_manager.py manages ~/.jarvis/projects.db (SQLite, no external deps).
4-tier fuzzy name matching. 10 actions (see action table above).
PROJECT_FOCUS uses claude-haiku to reason over priorities, blockers, and timestamps.
Morning briefing appends a project snapshot if any active projects exist.

---

## Reminder system (Sprint 8)

reminders.py manages time-based reminders in ~/.jarvis/reminders.db.
Scheduler polls every 30s. Fires: notify_windows() + TTS on all active WS connections.

---

## Gmail integration (Sprint 7)

mail_gmail.py reads Gmail via OAuth. Token at ~/.jarvis/gmail_token.json.
Actions: READ_MAIL (list recent), SUMMARIZE_MAIL (AI summary of inbox)

---

## Conversation persistence

conversation_db.py stores every turn in ~/.jarvis/conversations.db (SQLite).
Last 20 messages loaded on WS connect. DB pruned to 200 rows max.

---

## Frontend state machine

idle -> listening -> thinking -> speaking -> idle

- status:idle from server is IGNORED while in speaking state.
- speakingWatchdog: 30s timeout forces idle if stuck in speaking state.
- {type:"text"} triggers browser TTS fallback.
- {type:"audio"} with valid base64 MP3 cancels browser TTS and plays Fish Audio.

---

## Environment variables (.env)

```
ANTHROPIC_API_KEY=
FISH_API_KEY=
FISH_VOICE_ID=612b878b113047d9a770c069c8b4fdfe
USER_LOCATION=San Juan, Puerto Rico
DEV_MODE=1

# Whisper ASR (Sprint 18)
WHISPER_MODEL=tiny        # tiny / base / small / medium

# OBS WebSocket
OBS_PORT=4455
OBS_PASSWORD=your_obs_ws_password
OBS_MIC_INPUT_NAME=Mic/Aux

# Stream Copilot scene names (optional -- falls back to keyword scan)
STREAM_STARTING_SCENE=Starting Soon
STREAM_GAMEPLAY_SCENE=Gameplay
STREAM_BRB_SCENE=BRB
STREAM_SAFE_SCENE=Safe Scene
STREAM_ENDING_SCENE=Ending Screen
STREAM_BRB_MUTES_MIC=true
STREAM_PANIC_STOPS_STREAM=false

# Brave Search
BRAVE_SEARCH_API_KEY=

# Spotify
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Budget
BUDGET_FOLDER=/mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/Payoff debts/
```

---

## Dev scripts

| Script | Purpose |
|--------|---------|
| verify_jarvis.sh | Full smoke test -- run after every pull or before pushing |
| build_frontend.sh | Builds frontend via nvm-aware bash (use when npm run build fails from PowerShell) |
| typecheck_frontend.sh | TypeScript type-check only |
| setup_dev_env.sh | First-time setup on a new machine (npm install + import check) |

**Start JARVIS:**
```bash
# Terminal 1 -- backend
cd ~/dev/jarvis/jarvis && DEV_MODE=1 python3 server.py

# Terminal 2 -- frontend (dev mode)
cd ~/dev/jarvis/jarvis/frontend && npm run dev

# Or build for production serving:
bash build_frontend.sh

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
| 5 | Browser search fix (explorer.exe ? bug), frontend stuck-state fix, settings |
| 6 | Browser TTS fallback, clipboard read/write, conversation persistence (SQLite) |
| 7 | Gmail integration (OAuth, read + AI summarize inbox) |
| 8 | Reminder system + Windows notifications; Google Calendar read via OAuth |
| 9 | Morning Briefing, Daily Overview, What Next (weather + calendar + mail) |
| 10 | Web Search via Brave API (freshness for live data); OBS Studio WebSocket control |
| 11 | Stream Copilot macros: go_live, brb_mode, panic_mode, end_stream, stream_prep |
| 12 | Spotify voice control: play/pause/skip/volume/search/queue via Spotify Web API |
| 13 | Budget Assistant: read local Excel financial dashboard, answer debt/payoff questions by voice |
| 14 | Project Management Intelligence: track projects, log updates, blockers, standup, focus recommendation |
| 15 | Frontend dashboard UI: Three.js orb, widget layout, dashboard/ambient CSS modes |
| 16 | Contextual UI System: ambient/dashboard/context modes, voice-triggered panels, 15s auto-dismiss |
| 17 | Orb fix (transparent WebGL canvas, CSS fallback), calendar widget, orb visibility in dashboard mode |
| 18 | Server-side Whisper ASR: faster-whisper backend, MediaRecorder+VAD frontend, auto-selects over browser STT |

---

## Common issues & fixes

**Search opens File Explorer**: explorer.exe treats ? as a wildcard.
  Fixed by using PowerShell Start-Process for all URL opening.

**OBS connection refused from WSL**: Two causes:
  1. Wrong Windows IP (using DNS nameserver instead of default gateway). Fixed in obs_controller.py.
  2. Windows Firewall blocking port 4455 from WSL subnet. Add inbound rule (see WSL2 Networking).

**OAuth insecure transport error**: Set OAUTHLIB_INSECURE_TRANSPORT=1 in .env for local dev.

**Calendar 403 accessNotConfigured**: Enable Google Calendar API at console.cloud.google.com.

**Calendar token stale after scope change**: Delete token_calendar.json and re-auth.

**Spotify auth needed**: First time, say "play something" and complete OAuth in browser.

**Brave Search returning stale prices/scores**: Ensure BRAVE_SEARCH_API_KEY is set (not
  commented out) in .env.

**stop_stream false positive**: phrase must LEAD the sentence (no substring match).

**switch_scene false positive**: pronoun targets (it, that, this, there) are filtered out.

**Frontend stuck in speaking**: Fixed by ignoring server idle signals while currentState === "speaking".

**Multi-line git commits in PowerShell**: heredoc syntax is rejected.
  Workaround: write commit message to a temp file, use git commit -F.
  OR use build_frontend.sh pattern (write script to WSL path, run via wsl bash /path/to/script.sh).

**npm run build fails from PowerShell (UNC path error)**:
  PowerShell passes the UNC path (\\wsl.localhost\...) to CMD.EXE which doesn't support it.
  Fix: use build_frontend.sh written to the WSL path and run: wsl bash /home/jb/dev/jarvis/jarvis/build_frontend.sh

**pip --break-system-packages**: WSL pip 22.x does not support this flag.
  Use plain pip3 install -r requirements.txt.

**Vite proxy SSL error (EPROTO)**: Proxy target must be http:// not https://
  when backend runs with DEV_MODE=1. Already fixed in vite.config.ts.

**Whisper model first-load slow**: tiny model (~75 MB) downloads on first preload() call.
  Subsequent starts use the cached model. Use WHISPER_MODEL=tiny for fastest startup.

**Whisper transcription quality poor**: Upgrade model size (base or small) via WHISPER_MODEL env var.
  Tradeoff: larger model = better accuracy but more CPU and memory.

**OBS log spam on machines without OBS configured**:
  Added 60s backoff after failed connect. See _last_fail_ts in obs_controller.py.

**Web Speech API wedges silently (continuous mode)**:
  Fixed with 12s heartbeat in voice.ts: forceRestart() if no activity detected.

**Mic accuracy is per-machine (Web Speech API path)**:
  Whisper ASR (Sprint 18) eliminates this issue entirely by running locally on server.

**Frontend dist out of date when switching machines**:
  FastAPI serves frontend/dist/ via StaticFiles. Always run build_frontend.sh after pulling UI changes.

---

## Session handoff — May 13, 2026

Latest commits on origin/main (Sprint 18 complete):
  e6e0a8c  Sprint 18: Whisper ASR backend — whisper_stt.py + server.py endpoints
  dccc625  Sprint 18: Whisper ASR frontend — whisperVoice.ts + main.ts auto-detection

To pick up on any machine:
  git pull
  bash build_frontend.sh
  DEV_MODE=1 python3 server.py

Planned next sprints:
  Sprint 19 — Email context panel: wire mail_gmail.fetch_recent_emails() into
              /api/dashboard/email + fetchEmailPanel() in ContextPanels.ts
  Sprint 20 — Deep Research agent: multi-hop Brave Search + Claude synthesis,
              new DEEP_RESEARCH action
