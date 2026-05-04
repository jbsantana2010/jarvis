# JARVIS — Complete Documentation

> Voice-activated AI assistant for Windows/WSL. Speak to it like Tony Stark speaks to JARVIS.

---

## Table of Contents

1. What JARVIS Can Do
2. System Requirements
3. Installation & First-Time Setup
4. Starting JARVIS
5. All Voice Commands Reference
6. Integrations Setup (Google, OBS, Spotify, Brave)
7. Stream Copilot Guide
8. Troubleshooting
9. Sprint 13 Recommendation

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
- List, cancel, and snooze reminders
- Add notes and tasks

**Web Search**
- Search the web via Brave Search API
- Automatically uses fresh results for time-sensitive queries (prices, scores, news)
- Warns you when data might be slightly delayed (e.g. crypto prices)

**OBS / Streaming**
- Check OBS connection status
- Start and stop streams and recordings
- Switch scenes, list all scenes
- Toggle microphone mute
- Stream Copilot macros (see Section 7)

**Spotify**
- Play, pause, skip, go back
- Set volume
- Play any artist, song, or playlist by name ("play some lo-fi hip hop")
- Queue a specific track
- Ask what is currently playing

**Project Management**
- Track any number of active projects with name, priority, and status
- Log voice updates to a project ("log update on JARVIS: finished sprint 14")
- Flag blockers and resolve them by voice
- Get a cross-project standup in seconds
- Ask JARVIS what you should work on next — it reasons across priorities, blockers, and recent activity
- Weekly digest: what you accomplished across all projects this week
- Find projects you haven't touched in a while

**Developer Tools**
- Start a work session (routes speech to Claude Code for coding help)
- Dispatch tasks to Claude Code projects by name
- Build and research projects by voice

---

## 2. System Requirements

### Hardware / OS
- Windows 10 or 11 with WSL2 enabled
- At least 4 GB RAM for comfortable operation
- Microphone (any — browser Web Speech API handles STT)

### Software (Windows side)
- WSL2 with Ubuntu (or similar Linux distro)
- Node.js 18+ (in WSL)
- Python 3.10+ (in WSL)
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
```

Key packages: fastapi, uvicorn, anthropic, websockets, spotipy, obsws-python,
google-auth-oauthlib, google-api-python-client, httpx, python-dotenv

### Step 3 — Install frontend dependencies
```bash
cd frontend
npm install
cd ..
```

### Step 4 — Create your .env file
Copy .env.example to .env and fill in your keys:
```
ANTHROPIC_API_KEY=sk-ant-...
FISH_API_KEY=...
FISH_VOICE_ID=612b878b113047d9a770c069c8b4fdfe
USER_LOCATION=San Juan, Puerto Rico
DEV_MODE=1
BRAVE_SEARCH_API_KEY=...

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
```

### Step 5 — Google OAuth setup (Calendar + Gmail)
1. Go to console.cloud.google.com
2. Create a project (or use existing)
3. Enable "Google Calendar API" and "Gmail API"
4. Create OAuth 2.0 Desktop credentials
5. Download credentials.json and place in the jarvis/ folder
6. First time JARVIS runs, it will open your browser for consent

### Step 6 — OBS WebSocket setup (streaming only)
1. Open OBS → Tools → WebSocket Server Settings
2. Enable WebSocket server, set port 4455, set a password
3. Add that password to OBS_PASSWORD in .env
4. Run this in an elevated PowerShell on Windows to allow WSL through the firewall:
```powershell
New-NetFirewallRule -DisplayName "OBS WebSocket WSL" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Allow
```

### Step 7 — Spotify Developer app setup (Spotify only)
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

**Terminal 2 — Frontend**
```bash
cd ~/dev/jarvis/jarvis/frontend
npm run dev
```

**Browser**
Open http://localhost:5173

You should see the JARVIS interface. Click the microphone or press Space to speak.
The status indicator shows: idle → listening → thinking → speaking → idle.

---

## 5. All Voice Commands Reference

You can speak naturally — these are just examples of what triggers each capability.
JARVIS understands context and paraphrase.

### General / Computer Control
| Say something like... | What happens |
|----------------------|-------------|
| "Open Discord" | Launches Discord on Windows |
| "Open Chrome" | Launches Chrome |
| "Open calculator" | Launches Windows Calculator |
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
| "What is my schedule this week?" | Lists this week's events |
| "What is my next event?" | Reads your very next calendar item |
| "Give me a daily overview" | Full rundown of today's schedule |
| "Add a dentist appointment Friday at 3pm" | Creates calendar event |
| "Schedule a team meeting tomorrow at 10am for one hour" | Creates event with end time |

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
| "Look up the weather in Tokyo" | Web search (or weather action) |

### OBS / Streaming
| Say something like... | What happens |
|----------------------|-------------|
| "Is OBS connected?" | Checks WebSocket status |
| "Start the stream" | Starts OBS streaming |
| "Stop the stream" | Stops OBS streaming |
| "Start recording" | Starts OBS recording |
| "Stop recording" | Stops OBS recording |
| "Switch to gameplay scene" | Switches OBS scene |
| "What scenes do I have?" | Lists all OBS scenes |
| "Mute my mic" / "Unmute my mic" | Toggles mic in OBS |

### Stream Copilot (macro sequences)
| Say... | What happens |
|--------|-------------|
| "Stream prep" | Starting scene + unmute mic + start recording |
| "Go live" | Start stream + recording + switch to gameplay |
| "BRB" / "Going BRB" | BRB scene + mute mic |
| "Panic" / "Emergency" | Safe scene + mute mic (+ stop stream if configured) |
| "End the stream" / "Stream outro" | Ending scene → pause → stop stream + recording |

### Project Tracking
- No setup required — DB is created automatically at ~/.jarvis/projects.db on first use
- Project names support fuzzy matching: say "jarvis" and it finds "JARVIS"
- Ambiguous names (matching 2+ projects) are flagged — JARVIS will ask you to be more specific

### Spotify
| Say something like... | What happens |
|----------------------|-------------|
| "What is playing?" | Shows current track and artist |
| "Play" / "Resume" | Resumes playback |
| "Pause" | Pauses Spotify |
| "Skip" / "Next song" | Skips to next track |
| "Go back" / "Previous song" | Goes to previous track |
| "Set volume to 60" | Sets volume to 60% |
| "Play some lo-fi hip hop" | Searches and plays matching playlist |
| "Play Drake" | Plays Drake's music |
| "Play Blinding Lights" | Plays the track |
| "Queue Bohemian Rhapsody" | Adds track to queue |
| "Play something chill" | Plays a chill vibes playlist |
| "Play focus music" | Plays a deep focus playlist |

### Project Management
| Say something like... | What happens |
|----------------------|-------------|
| "Add project JARVIS" | Registers JARVIS as a new active project |
| "Add project Budget Tracker, high priority" | Adds with high priority |
| "Start tracking my new app" | Same as add project |
| "Log update on JARVIS: finished the voice commands" | Appends a timestamped note |
| "What's the status of JARVIS?" | Full status: priority, last update, blockers |
| "Project standup" | All active projects with last update and blockers |
| "What should I work on next?" | AI recommends one specific next action |
| "JARVIS is blocked on needing a Spotify test" | Logs blocker |
| "Resolve blocker on JARVIS" | Clears the open blocker |
| "Mark Budget Tracker as done" | Sets project to complete |
| "Mark JARVIS as paused" | Pauses a project |
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
- First run: browser opens for OAuth consent
- Token saved to token_calendar.json
- If you see permission errors: delete token_calendar.json and restart

### Gmail
- Same credentials.json as Calendar
- Token saved to ~/.jarvis/gmail_token.json
- First run: browser opens for OAuth consent

### OBS Studio
- OBS must be running before JARVIS starts
- WebSocket server enabled in OBS settings (port 4455)
- Password in OBS_PASSWORD env var
- Windows Firewall rule required (see Installation Step 6)
- Scene names in .env must exactly match your OBS scene names (or JARVIS will keyword-scan)

### Brave Search
- Sign up at api.search.brave.com (free tier available)
- Add key to BRAVE_SEARCH_API_KEY in .env
- Do NOT comment out the key with # — it must be an active line

### Project Tracking
- No setup required — DB is created automatically at ~/.jarvis/projects.db on first use
- Project names support fuzzy matching: say "jarvis" and it finds "JARVIS"
- Ambiguous names (matching 2+ projects) are flagged — JARVIS will ask you to be more specific

### Spotify
- Spotify desktop app must be open and signed in
- Developer app created at developer.spotify.com
- Requires Premium account for playback control
- First use: browser opens for OAuth consent; token saved to token_spotify.json

---

## 7. Stream Copilot Guide

Stream Copilot turns complex multi-step OBS sequences into single voice commands.

### Scene Name Configuration
JARVIS looks up your actual scene names two ways:
1. **Env var** (preferred): set the exact name in .env, e.g. `STREAM_GAMEPLAY_SCENE=Gameplay`
2. **Keyword scan** (fallback): JARVIS scans your scene list and picks the best match

Set these in your .env to match your OBS scene names exactly:
```
STREAM_STARTING_SCENE=Starting Soon
STREAM_GAMEPLAY_SCENE=Gameplay
STREAM_BRB_SCENE=BRB
STREAM_SAFE_SCENE=Safe Scene
STREAM_ENDING_SCENE=Ending Screen
```

### Macro Details

**Stream Prep** ("stream prep", "get me ready to stream")
1. Switches to your Starting scene
2. Unmutes microphone
3. Starts recording
Does NOT start the stream — use "go live" for that.

**Go Live** ("go live", "start the stream", "start streaming")
1. Starts OBS stream
2. Starts OBS recording
3. Waits 1.5 seconds
4. Switches to Gameplay scene

**BRB Mode** ("BRB", "going BRB", "be right back")
1. Switches to BRB scene
2. Mutes microphone (if STREAM_BRB_MUTES_MIC=true)

**Panic Mode** ("panic", "emergency", "something went wrong")
Soft (default): Switches to Safe scene + mutes mic
Hard (STREAM_PANIC_STOPS_STREAM=true): Also stops the stream immediately

**End Stream** ("end the stream", "stream outro", "end stream safe")
1. Switches to Ending scene
2. Waits 2 seconds (so viewers see the outro)
3. Stops OBS stream
4. Stops OBS recording

### Safety Features
- Mic mute is explicit (set to state, not toggle) to avoid double-toggle bugs
- If a scene is not found, that step is skipped gracefully — the macro continues
- "stop the stream" only fires if those words LEAD your sentence (prevents false positives)

---

## 8. Troubleshooting

**JARVIS is not responding to voice**
- Make sure the browser has microphone permission
- Check Terminal 1 for Python errors
- Confirm DEV_MODE=1 is set

**OBS says "connection refused"**
- Is OBS running? The app must be open
- Is WebSocket server enabled in OBS settings?
- Did you add the Windows Firewall rule? (Run in elevated PowerShell)
- Restart JARVIS after adding the firewall rule

**Calendar says "access not configured"**
- Enable Google Calendar API at console.cloud.google.com for your project

**Calendar token not working after changes**
- Delete token_calendar.json and restart JARVIS to re-authorize

**Spotify says "needs auth"**
- Say "play something" and complete the browser OAuth flow
- Make sure Spotify desktop app is open and playing on a device

**Web search returns no results or stale prices**
- Check BRAVE_SEARCH_API_KEY is in .env and is NOT commented out
- Verify the key at api.search.brave.com

**JARVIS accidentally stopped the stream**
- This is a fast-path false positive. The fix is in place (leading-phrase match only)
- If it still happens, note the exact phrase and report it for a fix

**Voice sounds robotic / TTS fallback**
- FISH_API_KEY may be missing or over quota
- JARVIS falls back to browser speech synthesis automatically

**"pip install" fails with --break-system-packages**
- WSL Ubuntu pip does not support that flag
- Use: pip3 install -r requirements.txt (no extra flags)

---

## 9. Sprint 15 Recommendation: Budget + Project Intelligence Enhancements

### Completed
Sprints 13 and 14 are done. Sprint 13 added budget analysis from your local Excel file. Sprint 14 added full project management intelligence.

### Sprint 15 Ideas so you can
ask questions like "how much do I owe on my car loan?" or "what is my total debt?"
and get instant spoken answers.

### Your Budget Files
Location: C:\Users\jbsan\OneDrive\Documents\Payoff debts\Payoff debts\

JARVIS should be able to:
- Read Excel/CSV files from that folder (accessible in WSL via /mnt/c/...)
- Parse debt names, balances, interest rates, minimum payments
- Answer natural language questions about your financial status
- Track progress over time (compare current vs previous month)
- Suggest payoff strategies (avalanche: highest interest first; snowball: lowest balance first)
- Create a budget snapshot on demand ("give me a budget summary")

### New Actions to Add
| Action | What it does |
|--------|-------------|
| BUDGET_SUMMARY | Read all budget files and speak a debt overview |
| BUDGET_PAYOFF_PLAN | Calculate and speak an optimal payoff strategy |
| BUDGET_DEBT_STATUS debt_name | Speak the current balance/rate for one debt |
| BUDGET_PROGRESS | Compare this month vs last snapshot |

### New Files to Create
- budget_reader.py — scans the OneDrive folder, parses Excel/CSV files with openpyxl/pandas
- budget_analyzer.py — debt summary, payoff calculations, trend comparison

### Key Technical Decisions
- File path: /mnt/c/Users/jbsan/OneDrive/Documents/Payoff debts/Payoff debts/
- Use openpyxl for .xlsx, csv module for .csv
- Store snapshots in ~/.jarvis/budget_snapshots/ (JSON) for trend tracking
- No new OAuth needed — direct file access

### Voice Examples After Sprint 13
- "What is my total debt?"
- "How much do I owe on my credit cards?"
- "Give me a budget summary"
- "What is the best way to pay off my debt?"
- "How much have I paid down this month?"
- "Show me my payoff plan"

### Estimated Scope
Medium sprint — 2-3 hours of work. The main complexity is parsing whatever
format your budget files are in (Excel columns, CSV structure). Once the reader
is working, the voice integration is straightforward.

---

*JARVIS documentation — last updated Sprint 12*
