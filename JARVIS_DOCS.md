# JARVIS — Complete Documentation

> Voice-activated AI assistant for Windows/WSL. Speak to it like Tony Stark speaks to JARVIS.

*Last updated: Sprint 18 — May 2026*

---

## Table of Contents

1. What JARVIS Can Do
2. System Requirements
3. Installation & First-Time Setup
4. Starting JARVIS
5. All Voice Commands Reference
6. Integrations Setup (Google, OBS, Spotify, Brave)
7. Stream Copilot Guide
8. Whisper ASR Setup (Sprint 18)
9. Dashboard & UI Modes (Sprints 15–17)
10. Troubleshooting

---

## 1. What JARVIS Can Do

JARVIS is a voice-first AI assistant that runs on your Windows PC (via WSL). You speak to it through a browser tab; it hears you, thinks with Claude AI, and responds with a natural voice. Beyond conversation, it can control your computer, apps, calendar, email, music, and livestream setup.

### Capabilities Summary

**General AI**
- Have natural conversations — JARVIS remembers context within a session
- Answer questions, explain concepts, do research
- Remember facts about you ("remember I prefer dark mode")

**Your Computer**
- Open any Windows app by name ("open Discord", "launch Spotify", "open calculator")
- Open websites and do browser searches
- Read and write your clipboard
- Take a screenshot and describe what it sees

**Calendar & Email**
- Read your Google Calendar — today, this week, upcoming events
- Create new calendar events ("add a dentist appointment Thursday at 2pm")
- Read your Gmail inbox and give an AI summary of what matters
- Morning briefing: weather + today's schedule + email summary in one shot

**Reminders & Tasks**
- Set timed reminders ("remind me in 20 minutes to take a break")
- List and cancel reminders
- Add notes and tasks

**Web Search**
- Search the web via Brave Search API
- Automatically uses fresh results for time-sensitive queries (prices, scores, news)

**OBS / Streaming**
- Check OBS connection status, start/stop streams and recordings
- Switch scenes, list all scenes, toggle microphone mute
- Stream Copilot macros (see Section 7)

**Spotify**
- Play, pause, skip, go back; set volume
- Play any artist, song, or playlist by name
- Queue tracks; ask what is currently playing

**Budget**
- Reads your local Excel financial dashboard (OneDrive)
- Total debt, breakdown by debt, avalanche/snowball payoff plan
- Highest interest debt, monthly payment calendar

**Project Management**
- Track any number of active projects with name, priority, and status
- Log voice updates, flag blockers, resolve them
- Cross-project standup, weekly digest, AI focus recommendation

**Developer Tools**
- Start a work session (routes speech to Claude Code for coding help)
- Dispatch tasks to Claude Code projects by name

---

## 2. System Requirements

### Hardware / OS
- Windows 10 or 11 with WSL2 enabled
- At least 4 GB RAM (8 GB recommended if using Whisper ASR)
- Microphone (any — Whisper ASR handles STT server-side)

### Software (WSL side)
- WSL2 with Ubuntu (or similar Linux distro)
- Node.js 18+ (in WSL, via nvm recommended)
- Python 3.10+ (in WSL)
- faster-whisper: `pip3 install faster-whisper`
- OBS Studio 28+ (if using streaming features) with WebSocket plugin enabled
- Spotify desktop app running (if using Spotify control)

### API Keys Required
| Key | Where to get it | Used for |
|-----|----------------|---------|
| ANTHROPIC_API_KEY | console.anthropic.com | Core AI reasoning |
| FISH_API_KEY | fish.audio | Voice TTS |
| BRAVE_SEARCH_API_KEY | api.search.brave.com | Web search |
| SPOTIFY_CLIENT_ID + SECRET | developer.spotify.com | Spotify control |

### Google OAuth (for Calendar + Gmail)
- Google Cloud project with Calendar API and Gmail API enabled
- OAuth 2.0 credentials (credentials.json) downloaded into project root
- First run of each integration opens a browser for OAuth consent

---

## 3. Installation & First-Time Setup

### Step 1 — Clone the repo (WSL terminal)
```bash
cd ~/dev
git clone <your-repo-url> jarvis
cd jarvis/jarvis
```

### Step 2 — Install Python dependencies
```bash
pip3 install -r requirements.txt
pip3 install faster-whisper   # Sprint 18 — server-side ASR
```

### Step 3 — Install frontend dependencies
```bash
cd frontend
npm install
cd ..
```

### Step 4 — Build the frontend
```bash
bash build_frontend.sh
```

### Step 5 — Create your .env file
Copy .env.example to .env and fill in your keys:
```
ANTHROPIC_API_KEY=sk-ant-...
FISH_API_KEY=...
FISH_VOICE_ID=612b878b113047d9a770c069c8b4fdfe
USER_LOCATION=San Juan, Puerto Rico
DEV_MODE=1
BRAVE_SEARCH_API_KEY=...

# Whisper ASR model size (tiny is fastest; base/small/medium = more accurate)
WHISPER_MODEL=tiny

# OBS (if streaming)
OBS_PORT=4455
OBS_PASSWORD=your_obs_ws_password
OBS_MIC_INPUT_NAME=Mic/Aux

# Stream scene names (adjust to match your actual OBS scene names)
STREAM_STARTING_SCENE=Starting Soon
STREAM_GAMEPLAY_SCENE=Gameplay
STREAM_BRB_SCENE=BRB
STREAM_SAFE_SCENE=Safe Scene
STREAM_ENDING_SCENE=Ending Screen
STREAM_BRB_MUTES_MIC=true
STREAM_PANIC_STOPS_STREAM=false

# Spotify
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Budget file location (OneDrive path)
BUDGET_FOLDER=/mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/Payoff debts/
```

### Step 6 — Google OAuth setup (Calendar + Gmail)
1. Go to console.cloud.google.com
2. Create a project (or use existing)
3. Enable "Google Calendar API" and "Gmail API"
4. Create OAuth 2.0 Desktop credentials
5. Download credentials.json and place in the jarvis/ folder
6. First time JARVIS runs, it will open your browser for consent

### Step 7 — OBS WebSocket setup (streaming only)
1. Open OBS → Tools → WebSocket Server Settings
2. Enable WebSocket server, set port 4455, set a password
3. Add that password to OBS_PASSWORD in .env
4. Run this in an elevated PowerShell on Windows to allow WSL through the firewall:
```powershell
New-NetFirewallRule -DisplayName "OBS WebSocket WSL" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Allow
```

### Step 8 — Spotify Developer app setup (Spotify only)
1. Go to developer.spotify.com and create an app
2. Set Redirect URI to: http://localhost:8888/callback
3. Copy Client ID and Client Secret to .env
4. Requires Spotify Premium for playback control

---

## 4. Starting JARVIS

Open two WSL terminals:

**Terminal 1 — Backend**
```bash
cd ~/dev/jarvis/jarvis
DEV_MODE=1 python3 server.py
```

**Terminal 2 — Frontend (dev)**
```bash
cd ~/dev/jarvis/jarvis/frontend
npm run dev
```

**Browser**
Open http://localhost:5173

Click anywhere on the interface to activate. JARVIS will auto-detect whether to use
server-side Whisper ASR or fall back to browser speech recognition. The status bar shows
`whisper` when Whisper ASR is active.

---

## 5. All Voice Commands Reference

### General / Computer Control
| Say something like... | What happens |
|----------------------|-------------|
| "Open Discord" | Launches Discord on Windows |
| "Open Chrome" | Launches Chrome |
| "Search for cheap flights to Miami" | Opens browser search |
| "Go to youtube.com" | Opens YouTube in browser |
| "Read my clipboard" | Reads whatever is on your clipboard |
| "Copy 'Hello World' to clipboard" | Writes text to clipboard |
| "Take a screenshot" | Captures screen and describes it |
| "Remember I wake up at 7am" | Stores a personal fact |

### Calendar
| Say something like... | What happens |
|----------------------|-------------|
| "What is on my calendar today?" | Lists today's events |
| "What is my next event?" | Reads your very next calendar item |
| "Give me a daily overview" | Full rundown of today's schedule |
| "Add a dentist appointment Friday at 3pm" | Creates calendar event |

### Email
| Say something like... | What happens |
|----------------------|-------------|
| "Check my email" | Lists recent Gmail messages |
| "Summarize my inbox" | AI summary of what matters |
| "Good morning" / "Morning briefing" | Weather + calendar + email summary |

### Reminders
| Say something like... | What happens |
|----------------------|-------------|
| "Remind me in 30 minutes to drink water" | Sets a 30-min reminder |
| "Remind me at 5pm to call mom" | Sets a time-specific reminder |
| "What reminders do I have?" | Lists all pending reminders |

### Web Search
| Say something like... | What happens |
|----------------------|-------------|
| "What is the price of Bitcoin?" | Brave Search with freshness filter |
| "Who won the game last night?" | Fresh sports results |
| "Search for best Python async tutorials" | General web search |

### Budget
| Say something like... | What happens |
|----------------------|-------------|
| "Give me a budget summary" | Income, expenses, deficit, total debt |
| "How much do I owe?" | Total debt with top 3 balances |
| "Show me all my debts" | Full debt list with APR and minimums |
| "What is my payoff plan?" | Avalanche/snowball strategy |
| "Which debt has the highest interest?" | Highest APR debt details |
| "What is due this month?" | Payment calendar grouped by timing |

### OBS / Streaming
| Say something like... | What happens |
|----------------------|-------------|
| "Is OBS connected?" | Checks WebSocket status |
| "Start the stream" | Starts OBS streaming |
| "Stop the stream" | Stops OBS streaming |
| "Switch to gameplay scene" | Switches OBS scene |
| "What scenes do I have?" | Lists all OBS scenes |
| "Mute my mic" / "Unmute my mic" | Toggles mic in OBS |

### Stream Copilot (macro sequences)
| Say... | What happens |
|--------|-------------|
| "Stream prep" | Starting scene + unmute mic + start recording |
| "Go live" | Start stream + recording + switch to gameplay |
| "BRB" / "Going BRB" | BRB scene + mute mic |
| "Panic" / "Emergency" | Safe scene + mute mic |
| "End the stream" | Ending scene → pause → stop stream + recording |

### Spotify
| Say something like... | What happens |
|----------------------|-------------|
| "What is playing?" | Shows current track and artist |
| "Play" / "Pause" / "Skip" / "Previous" | Playback control |
| "Set volume to 60" | Sets volume to 60% |
| "Play some lo-fi hip hop" | Searches and plays matching playlist |
| "Play Drake" | Plays Drake's music |
| "Queue Bohemian Rhapsody" | Adds track to queue |
| "Play something chill" | Plays a chill vibes playlist |

### Project Management
| Say something like... | What happens |
|----------------------|-------------|
| "Add project JARVIS" | Registers JARVIS as a new active project |
| "Log update on JARVIS: finished sprint 18" | Appends a timestamped note |
| "What's the status of JARVIS?" | Full status: priority, last update, blockers |
| "Project standup" | All active projects with last update and blockers |
| "What should I work on next?" | AI recommends one specific next action |
| "JARVIS is blocked on needing a Spotify test" | Logs blocker |
| "Resolve blocker on JARVIS" | Clears the open blocker |
| "Mark Budget Tracker as done" | Sets project to complete |
| "What did I accomplish this week?" | Weekly digest from all logged updates |
| "What projects haven't I touched?" | Lists neglected projects |

### Developer / Work Mode
| Say... | What happens |
|--------|-------------|
| "Start work mode" | Routes speech to Claude Code coding assistant |
| "Stop work mode" | Returns to normal JARVIS mode |
| "Open terminal" | Opens Windows Terminal with Claude Code |

---

## 6. Integrations Setup Summary

### Google Calendar
- credentials.json must be in project root
- First run: browser opens for OAuth consent → token_calendar.json created
- If you see permission errors: delete token_calendar.json and restart

### Gmail
- Same credentials.json as Calendar
- Token saved to ~/.jarvis/gmail_token.json

### OBS Studio
- OBS must be running before JARVIS starts
- WebSocket server enabled in OBS settings (port 4455)
- Windows Firewall rule required (see Installation Step 7)

### Brave Search
- Sign up at api.search.brave.com (free tier available)
- Add key to BRAVE_SEARCH_API_KEY in .env

### Spotify
- Spotify desktop app must be open and signed in
- Developer app created at developer.spotify.com
- Requires Premium account for playback control
- First use: browser opens for OAuth → token_spotify.json created

### Budget
- Place your Excel financial dashboard in the path set by BUDGET_FOLDER in .env
- No OAuth needed — direct file access via WSL /mnt/c/ path
- JARVIS re-reads the file on every request (no stale cache)

### Project Tracking
- No setup required — DB created automatically at ~/.jarvis/projects.db on first use
- Fuzzy name matching: "jarvis" finds "JARVIS"

---

## 7. Stream Copilot Guide

Stream Copilot turns complex multi-step OBS sequences into single voice commands.

### Scene Name Configuration
Set these in your .env to match your OBS scene names exactly:
```
STREAM_STARTING_SCENE=Starting Soon
STREAM_GAMEPLAY_SCENE=Gameplay
STREAM_BRB_SCENE=BRB
STREAM_SAFE_SCENE=Safe Scene
STREAM_ENDING_SCENE=Ending Screen
```
JARVIS falls back to keyword scanning your actual scene list if env vars aren't set.

### Macro Details

**Stream Prep** — "stream prep", "get me ready to stream"
1. Switches to Starting scene → Unmutes mic → Starts recording

**Go Live** — "go live", "start streaming"
1. Starts OBS stream + recording → waits 1.5s → Switches to Gameplay scene

**BRB Mode** — "BRB", "going BRB"
1. Switches to BRB scene → Mutes mic

**Panic Mode** — "panic", "emergency"
- Soft (default): Safe scene + mute mic
- Hard (STREAM_PANIC_STOPS_STREAM=true): Also stops the stream

**End Stream** — "end the stream", "stream outro"
1. Ending scene → 2s pause → Stop stream → Stop recording

---

## 8. Whisper ASR Setup (Sprint 18)

Sprint 18 replaced the browser's Web Speech API with server-side faster-whisper. This gives consistent transcription quality across all machines and microphones.

### How it works
1. The browser captures raw audio via MediaRecorder (webm/opus)
2. A VAD (Voice Activity Detector) watches the audio energy level
3. When speech is detected and then 700ms of silence follows, the audio clip is sent to the server
4. The server runs faster-whisper and returns the transcript
5. JARVIS processes the transcript exactly as before

### Install
```bash
pip3 install faster-whisper
```
The model (~75 MB for tiny) downloads automatically the first time the server starts.

### Model sizes
| Model | Size | Speed | Accuracy |
|-------|------|-------|---------|
| tiny | 75 MB | Fastest | Good for clear speech |
| base | 145 MB | Fast | Better for accents |
| small | 465 MB | Medium | Very good |
| medium | 1.5 GB | Slower | Excellent |

Set via WHISPER_MODEL in .env. Default is `tiny`.

### Fallback
If faster-whisper is not installed or fails to load, JARVIS automatically falls back to the browser's Web Speech API — no configuration needed. The fallback is transparent to the user.

### VAD tuning
The VAD uses RMS energy thresholding:
- Speech threshold: 0.012 RMS (above = speech, below = silence)
- Silence timeout: 700ms (how long silence must last to end an utterance)
- Min utterance: 200ms / Min blob: 1KB (filters out noise blips)

If JARVIS is not picking up soft speech, you may need to increase your mic input level in Windows Sound Settings.

---

## 9. Dashboard & UI Modes (Sprints 15–17)

JARVIS has three UI modes, controlled by voice or click:

### Ambient Mode (default after activation)
- Shows only the animated orb + a small pill indicator in the corner
- Minimal, unobtrusive — stays out of your way while you work
- Click the pill to switch to Dashboard

### Dashboard Mode
- Full layout: orb + all widgets (Calendar, Spotify, OBS, Projects)
- Calendar widget shows today's events and refreshes every 5 minutes
- Voice state (listening/thinking/speaking) shown on the orb

### Context Mode
Triggered automatically when you say certain phrases:
| Say... | Panel shown |
|--------|------------|
| "go live", "start stream", "obs" | OBS status panel |
| "what's playing", "spotify", "skip track" | Spotify panel |
| "my debt", "budget", "my balance" | Budget panel |
| "my projects", "what should I work on" | Projects panel |
| "check email", "my inbox" | Email panel |

The panel auto-dismisses after 15 seconds (animated countdown bar). Click X to dismiss early.

### Orb states
The orb color changes to reflect what JARVIS is doing:
- Dim blue → idle
- Bright blue → listening
- Purple → thinking
- Green → speaking

---

## 10. Troubleshooting

**JARVIS is not responding to voice**
- Make sure the browser has microphone permission (check the address bar lock icon)
- Check Terminal 1 for Python errors
- Confirm DEV_MODE=1 is set in .env

**Whisper not transcribing**
- Check Terminal 1 for `[whisper] model loaded` on startup
- If not present, run: pip3 install faster-whisper
- Check browser console for POST /api/stt/transcribe errors

**Whisper transcription is inaccurate**
- Increase WHISPER_MODEL to `base` or `small` in .env
- Check Windows Sound Settings → Input → ensure correct mic is default and level is high enough

**Browser falls back to Web Speech API unexpectedly**
- Run: curl http://localhost:8000/api/stt/status — should return `{"available":true}`
- If available is false, faster-whisper failed to load (check server logs)

**OBS says "connection refused"**
- Is OBS running? WebSocket server enabled? Firewall rule added?
- Restart JARVIS after adding the firewall rule

**Calendar says "access not configured"**
- Enable Google Calendar API at console.cloud.google.com

**Spotify says "needs auth"**
- Say "play something" and complete the browser OAuth flow
- Make sure Spotify desktop app is open

**Frontend is out of date after git pull**
- Run: bash build_frontend.sh
- FastAPI serves the built dist/ — stale builds won't reflect new code

**Budget file not found**
- Check BUDGET_FOLDER in .env points to the correct OneDrive path
- Verify the path is accessible: ls "/mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/"

**Voice sounds robotic / TTS fallback active**
- FISH_API_KEY may be missing or over quota
- JARVIS falls back to browser speech synthesis automatically

**npm run build fails (UNC path error)**
- Don't run npm directly from PowerShell with a WSL UNC path
- Use: wsl bash /home/jb/dev/jarvis/jarvis/build_frontend.sh
