# JARVIS — Project Context for Claude

This file gives Claude full project context when starting a new session,
especially useful when switching between machines (home ↔ work laptop).
**Always read this file first before making any changes.**

---

## What this project is

A voice-activated AI assistant running on WSL/Windows. The user speaks → browser
captures audio via Web Speech API → WebSocket → FastAPI backend → Anthropic Claude
for reasoning → Fish Audio for TTS → MP3 streamed back to browser. Falls back to
browser-native window.speechSynthesis if Fish Audio fails.

Current sprint: **Sprint 14 complete** (Project Management Intelligence).

---

## Architecture

Browser (Vite + TypeScript)
  Web Speech API (STT)
  AudioContext (MP3 playback)
  window.speechSynthesis (TTS fallback)
  WebSocket -> FastAPI server (server.py)
                        |
                        +- Anthropic API (claude-haiku fast, claude-sonnet complex)
                        +- Fish Audio API (TTS -> MP3 bytes -> base64)
                        +- platform_adapter.py  (all WSL/Windows OS ops)
                        +- actions.py           (high-level action helpers)
                        +- mail_gmail.py        (Gmail read via OAuth)
                        +- calendar_google.py   (Google Calendar read+write via OAuth)
                        +- briefing.py          (morning briefing + daily overview)
                        +- search_web.py        (Brave Search API + freshness)
                        +- obs_controller.py    (OBS Studio via WebSocket v5)
                        +- stream_copilot.py    (multi-step OBS macro sequences)
                        +- spotify_controller.py (Spotify Web API via spotipy)
                        +- conversation_db.py   (SQLite conversation history)
                        +- reminders.py         (SQLite reminders + scheduler)

---

## Key files

| File | Purpose |
|------|---------|
| server.py | Main FastAPI app, WebSocket handler, all action executors, system prompt, scheduler |
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
| screen.py | Screenshot routing (WSL -> platform_adapter, macOS -> native) |
| dispatch_registry.py | Tracks background Claude Code build tasks |
| work_mode.py | Work session management (claude -p subprocess) |
| frontend/src/main.ts | WebSocket client, state machine, audio playback, browser TTS fallback |
| frontend/src/voice.ts | AudioContext queue player |
| frontend/src/settings.ts | Settings panel (preferences API) |
| verify_jarvis.sh | Full smoke test -- always run after a pull or before pushing |

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

**Fast-path safety rules (critical):**
- STOP_STREAM and STOP_RECORDING: phrase must LEAD the sentence (no substring match)
- SWITCH_SCENE: filters pronoun-only targets (it, that, this, there, etc.)

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

Haiku prompt instructs: "For prices, scores, or live data: always state the value
AND note if the result may be delayed."

Action: [ACTION:WEB_SEARCH] bitcoin price today
Fast-path: "search for", "look up", "google", "what is the price of", "who won"

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

  stream_prep()     -- starting scene + unmute mic + start recording (no stream start)
  go_live()         -- start stream + recording + 1.5s pause + switch to gameplay scene
  brb_mode()        -- BRB scene + mute mic (STREAM_BRB_MUTES_MIC=true in .env)
  panic_mode()      -- soft: safe scene + mute / hard: also stop stream (STREAM_PANIC_STOPS_STREAM)
  end_stream_safe() -- ending scene + 2s pause + stop stream + stop recording

_find_scene(env_key, *keywords):
  1. Checks env var (e.g. STREAM_GAMEPLAY_SCENE) for exact scene name
  2. Falls back to keyword scan of actual OBS scene list (case-insensitive)
  Returns None if no match found -- action skips gracefully.

_set_mic_muted(muted): explicit state (not toggle) using get_input_mute + set_input_mute.

Env vars for scene names:
  STREAM_STARTING_SCENE, STREAM_GAMEPLAY_SCENE, STREAM_BRB_SCENE,
  STREAM_SAFE_SCENE, STREAM_ENDING_SCENE
  STREAM_BRB_MUTES_MIC=true, STREAM_PANIC_STOPS_STREAM=false

---

## Spotify Control (Sprint 12)

spotify_controller.py uses spotipy (pip install spotipy) + Spotify Web API.
OAuth flow with WSGI callback server on 0.0.0.0 (WSL2-compatible).
Token cached at token_spotify.json in project root.

Required env vars: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
  (redirect URI must be registered in your Spotify Developer app)

Scopes: user-read-playback-state user-modify-playback-state user-read-currently-playing
Requires Spotify Premium for playback control.

Key functions:
  get_status()           -- currently playing track + artist + volume
  play(), pause()        -- resume / pause
  skip(), previous()     -- next / previous track
  set_volume(amount)     -- 0-100
  play_query(query)      -- search and play (prefers playlists for playlist queries,
                            artists for artist queries, else tracks)
  queue_query(query)     -- add track to queue

_MOOD_MAP maps natural phrases to search queries:
  "something chill" -> "chill vibes playlist"
  "focus music" -> "deep focus music playlist"
  etc.

_active_device_id(sp): returns active device, falls back to first available device.

Setup steps:
  1. Create app at developer.spotify.com
  2. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env
  3. Set SPOTIFY_REDIRECT_URI=http://localhost:8888/callback (register this in the app)
  4. Run JARVIS and say "play some music" -- browser will open for OAuth consent
  5. After auth, token is cached; subsequent requests work without browser

---

## Reminder system (Sprint 8)

reminders.py manages time-based reminders in ~/.jarvis/reminders.db.

Time parsing supports: "in 10 minutes", "in 2 hours", "at 6 PM",
"at 3:30 PM", "tomorrow at 9 AM". Returns None if unparseable.

Scheduler: _reminder_scheduler_loop() runs as asyncio.create_task at server boot.
Polls every 30 seconds. When a reminder fires:
  1. Marks it done immediately (prevents double-firing).
  2. Calls platform_adapter.notify_windows() -- visible even if browser closed.
  3. Speaks via TTS on all active WebSocket connections.

LLM action format: [ACTION:SET_REMINDER] in 10 minutes ||| stretch

---

## Gmail integration (Sprint 7)

mail_gmail.py reads Gmail via OAuth. Token at ~/.jarvis/gmail_token.json.
First run opens browser for OAuth consent.
Actions: READ_MAIL (list recent), SUMMARIZE_MAIL (AI summary of inbox)

---

## Conversation persistence

conversation_db.py stores every turn in ~/.jarvis/conversations.db (SQLite).
On WebSocket connect, last 20 messages loaded into history[] so JARVIS remembers
context across server restarts. DB pruned to 200 rows max.

---

## Work mode

"Start work mode" launches a claude -p subprocess (WorkSession). Subsequent
speech routes there as a coding assistant. Stop phrases like "stop work mode",
"end work session" return to normal voice mode.

---

## Frontend state machine

idle -> listening -> thinking -> speaking -> idle

- status:idle from server is IGNORED while in speaking state (prevents race
  where server finishes before audio playback completes).
- speakingWatchdog: 30s timeout forces idle if stuck in speaking state.
- {type:"text"} triggers browser TTS fallback (Fish Audio failure path).
- {type:"audio"} with valid base64 MP3 cancels browser TTS and plays Fish Audio.

---

## Environment variables (.env)

```
ANTHROPIC_API_KEY=
FISH_API_KEY=
FISH_VOICE_ID=612b878b113047d9a770c069c8b4fdfe
USER_LOCATION=San Juan, Puerto Rico
DEV_MODE=1

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
```

DEV_MODE=1 disables SSL (required for Vite proxy in dev). Do NOT set in production.

---

## Dev scripts

| Script | Purpose |
|--------|---------|
| verify_jarvis.sh | Full smoke test -- run after every pull or before pushing |
| typecheck_frontend.sh | TypeScript type-check only |
| setup_dev_env.sh | First-time setup on a new machine (npm install + import check) |

**Start JARVIS:**
```bash
# Terminal 1 -- backend
cd ~/dev/jarvis/jarvis && DEV_MODE=1 python3 server.py

# Terminal 2 -- frontend
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



---

## Project Management (Sprint 14)

project_manager.py manages a local SQLite DB at ~/.jarvis/projects.db.
No external dependencies. Schema designed for future export/sync.

### Schema
  projects         -- id, name, status (active/paused/done), priority (1/2/3), description, created_at, updated_at
  project_updates  -- append-only log: id, project_id, note, created_at
  project_blockers -- id, project_id, description, resolved (0/1), created_at, resolved_at

### Fuzzy name matching (4 tiers)
  1. Exact case-insensitive match
  2. Starts-with match
  3. Substring match
  4. difflib close match (cutoff 0.55)
  Fails clearly if multiple projects match at the same tier.

### Actions
| Action | Target format | What it does |
|--------|--------------|-------------|
| PROJECT_ADD | name [||| description ||| priority] | Register new project |
| PROJECT_STATUS | project_name | Full status: priority, last update, blockers, update count |
| PROJECT_LOG | project_name ||| note | Append timestamped update |
| PROJECT_BLOCKER | project_name ||| reason | Add open blocker |
| PROJECT_RESOLVE_BLOCKER | project_name [||| blocker_query] | Mark best-matching blocker resolved |
| PROJECT_SET_STATUS | project_name ||| done/paused/active | Change project status |
| PROJECT_STANDUP | (none) | All active projects: last update + blockers, grouped by priority |
| PROJECT_FOCUS | (none) | Haiku-powered recommendation of what to work on next |
| PROJECT_WEEKLY | (none) | All updates logged in the past 7 days, grouped by project |
| PROJECT_UNTOUCHED | (none) | Active projects not touched in last 5 days |

### Focus recommendation (PROJECT_FOCUS)
Uses claude-haiku to reason over:
  - All active project names, priorities, last update timestamps
  - Open blockers (blocked projects are skipped unless unblocking is the priority)
  - Current time of day
Returns a decisive 2-3 sentence spoken recommendation.

### Morning briefing integration
build_morning_briefing() appends get_projects_snapshot() to its output
if any active projects exist. Snapshot is one line: "N active projects,
M blocked — top priority: ProjectName."

### Fast-path voice triggers (no LLM round-trip)
  "add project X" / "start tracking X"     → PROJECT_ADD
  "status of X" / "how is project X"        → PROJECT_STATUS
  "log update on X: note"                   → PROJECT_LOG
  "X is blocked on reason"                  → PROJECT_BLOCKER
  "mark X as done/paused/active"            → PROJECT_SET_STATUS
  "project standup" / "how are my projects" → PROJECT_STANDUP
  "what should I work on next"              → PROJECT_FOCUS
  "what did I accomplish this week"         → PROJECT_WEEKLY
  "what projects haven't I touched"         → PROJECT_UNTOUCHED

### Priority values
  1 = high (urgent/critical/important)
  2 = medium (default)
  3 = low (someday)
  Specified by word when adding: "add project X high priority"

---

## Budget Assistant (Sprint 13)

Reads Juan_Financial_Dashboard.xlsx from a local OneDrive folder and answers
debt/budget questions by voice. Never hallucinates financial data — if the file
is missing or a column is absent, JARVIS says so clearly.

### Files
- budget_reader.py  — loads openpyxl, parses Debts / Snapshot / Calendar sheets
- budget_analyzer.py — calculates totals, payoff strategy, produces voice-friendly text

### Budget file location
Default: /mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/Payoff debts/
Override: set BUDGET_FOLDER in .env
File parsed: Juan_Financial_Dashboard.xlsx

### Sheets used
- Debts: 11 debts with priority, balance, APR, min payment, status (avalanche-ordered)
- Snapshot: monthly income, total expenses, net cash flow, total debt, debt-to-income
- Calendar: payment due dates with category tags

### Actions
| Action | Function called | What it says |
|--------|----------------|-------------|
| BUDGET_SUMMARY | async_budget_summary() | Income, outflow, deficit, total debt, interest burned, DTI |
| BUDGET_TOTAL_DEBT | async_total_debt() | Total with top-3 by balance + min payment total |
| BUDGET_SHOW_DEBTS | async_show_debts() | All 11 debts: name, balance, APR, minimum, status |
| BUDGET_PAYOFF_PLAN | async_payoff_plan() | Avalanche (or snowball if no APR), top-5 targets + special flags |
| BUDGET_HIGHEST_INTEREST | async_highest_interest() | Highest APR debt, balance, monthly cost |
| BUDGET_MONTHLY_DUE | async_monthly_due() | Total minimums grouped by early/mid/late month |

### Payoff strategy logic
- If any debts have APR data: use avalanche (highest APR first)
- If no APR data: use snowball (smallest balance first)
- Always flag: 0% APR debts (kill immediately), past-due debts (catch up first)
- Explains which method was used and why

### Fast-path phrases (no LLM needed)
- "total debt", "how much do I owe" -> BUDGET_TOTAL_DEBT
- "show my debts", "list my debts" -> BUDGET_SHOW_DEBTS
- "payoff plan", "debt strategy" -> BUDGET_PAYOFF_PLAN
- "highest interest", "highest APR" -> BUDGET_HIGHEST_INTEREST
- "monthly payments", "what is due this month" -> BUDGET_MONTHLY_DUE
- "budget summary", "financial summary" -> BUDGET_SUMMARY

### Dependencies
- openpyxl>=3.1.0 (added to requirements.txt)
- No OAuth, no external APIs -- pure local file access via WSL /mnt/c/ path

### Common issues
- "Budget file not found": check BUDGET_FOLDER in .env points to the .xlsx location
- openpyxl missing: pip3 install openpyxl --break-system-packages
- Stale data: JARVIS re-reads the file on every request (no caching)

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
  commented out) in .env. The key must NOT start with # .

**stop_stream false positive** (e.g. "best stop streaming service" triggered stop):
  Fixed: stop_stream and stop_recording phrases must LEAD the sentence.

**switch_scene false positive** (e.g. "you switched to it" triggered scene switch):
  Fixed: scene targets that are pronouns (it, that, this, there...) are filtered out.

**Frontend stuck in speaking**: Server sends status:idle before audio finishes playing.
  Fixed by ignoring server idle signals while currentState === "speaking".

**TTS fallback stuck 30s**: {type:"text"} was not triggering audio, state never left speaking.
  Fixed by wiring text messages to speakWithBrowserTts().

**Multi-line git commits in PowerShell**: heredoc syntax is rejected.
  Workaround: write commit message to a temp file, use git commit -F.

**pip --break-system-packages**: WSL pip 22.x does not support this flag.
  Use plain pip3 install -r requirements.txt.

**Vite proxy SSL error (EPROTO)**: Proxy target must be http:// not https://
  when backend runs with DEV_MODE=1. Already fixed in vite.config.ts.
