/**
 * JARVIS — Main entry point.
 *
 * Wires together the orb visualization, WebSocket communication,
 * speech recognition, and audio playback into a single experience.
 */

import { createOrb, type OrbState } from "./orb";
import { createVoiceInput, createAudioPlayer } from "./voice";
import { createSocket } from "./ws";
import { openSettings, checkFirstTimeSetup } from "./settings";
import "./style.css";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

type State = "idle" | "listening" | "thinking" | "speaking";
let currentState: State = "idle";
let isMuted = false;

// Safety watchdog: if we get stuck in "speaking" with no audio finishing,
// force-return to idle after this many ms (covers decode errors, dropped WS msgs, etc.)
let speakingWatchdog: ReturnType<typeof setTimeout> | null = null;
const SPEAKING_WATCHDOG_MS = 30_000;

const statusEl = document.getElementById("status-text")!;
const errorEl = document.getElementById("error-text")!;

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.style.opacity = "1";
  setTimeout(() => {
    errorEl.style.opacity = "0";
  }, 5000);
}

function updateStatus(state: State) {
  const labels: Record<State, string> = {
    idle: "",
    listening: "listening...",
    thinking: "thinking...",
    speaking: "",
  };
  statusEl.textContent = labels[state];
}

// ---------------------------------------------------------------------------
// Init components
// ---------------------------------------------------------------------------

const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
const orb = createOrb(canvas);

const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${wsProto}//${window.location.host}/ws/voice`;
const socket = createSocket(WS_URL);

const audioPlayer = createAudioPlayer();
orb.setAnalyser(audioPlayer.getAnalyser());

function transition(newState: State) {
  if (newState === currentState) return;

  // Clear watchdog whenever we leave speaking
  if (speakingWatchdog !== null && newState !== "speaking") {
    clearTimeout(speakingWatchdog);
    speakingWatchdog = null;
  }

  currentState = newState;
  orb.setState(newState as OrbState);
  updateStatus(newState);

  switch (newState) {
    case "idle":
      if (!isMuted) voiceInput.resume();
      break;
    case "listening":
      if (!isMuted) voiceInput.resume();
      break;
    case "thinking":
      voiceInput.pause();
      break;
    case "speaking":
      voiceInput.pause();
      // Start watchdog: force idle if audio never finishes (decode fail, lost WS msg, etc.)
      speakingWatchdog = setTimeout(() => {
        console.warn("[state] speaking watchdog fired — forcing idle");
        speakingWatchdog = null;
        transition("idle");
      }, SPEAKING_WATCHDOG_MS);
      break;
  }
}

// ---------------------------------------------------------------------------
// Voice input
// ---------------------------------------------------------------------------

const voiceInput = createVoiceInput(
  (text: string) => {
    // Cancel any current JARVIS response before sending new input
    audioPlayer.stop();
    // User spoke — send transcript
    socket.send({ type: "transcript", text, isFinal: true });
    transition("thinking");
  },
  (msg: string) => {
    showError(msg);
  }
);

// ---------------------------------------------------------------------------
// Audio playback finished
// ---------------------------------------------------------------------------

audioPlayer.onFinished(() => {
  transition("idle");
});

// ---------------------------------------------------------------------------
// Browser-native TTS fallback  (used when Fish Audio fails / key missing)
// ---------------------------------------------------------------------------

let _browserTtsUtterance: SpeechSynthesisUtterance | null = null;

function speakWithBrowserTts(text: string): void {
  if (!window.speechSynthesis) {
    console.warn("[tts-fallback] speechSynthesis not available — going idle");
    transition("idle");
    return;
  }

  // Cancel any existing utterance before starting a new one
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.92;   // slightly slower than default — more natural for JARVIS
  utterance.pitch = 0.95;
  utterance.volume = 1.0;

  utterance.onend = () => {
    _browserTtsUtterance = null;
    transition("idle");
  };
  utterance.onerror = (e) => {
    console.warn("[tts-fallback] utterance error:", e.error);
    _browserTtsUtterance = null;
    transition("idle");
  };

  _browserTtsUtterance = utterance;
  transition("speaking");
  window.speechSynthesis.speak(utterance);
  console.log("[tts-fallback] speaking via browser TTS:", text.slice(0, 60));
}

function cancelBrowserTts(): void {
  if (_browserTtsUtterance) {
    window.speechSynthesis.cancel();
    _browserTtsUtterance = null;
  }
}

// ---------------------------------------------------------------------------
// WebSocket messages
// ---------------------------------------------------------------------------

socket.onMessage((msg) => {
  const type = msg.type as string;

  if (type === "audio") {
    const audioData = msg.data as string;
    console.log("[audio] received", audioData ? `${audioData.length} chars` : "EMPTY", "state:", currentState);
    if (audioData) {
      // Real Fish Audio arriving — cancel any browser TTS fallback in progress
      cancelBrowserTts();
      if (currentState !== "speaking") {
        transition("speaking");
      }
      audioPlayer.enqueue(audioData);
    } else {
      // Server sent empty audio data — return to idle (browser TTS handled via "text" msg)
      console.warn("[audio] empty data received, returning to idle");
      transition("idle");
    }
    if (msg.text) console.log("[JARVIS]", msg.text);
  } else if (type === "text") {
    // Server sends {type:"text"} when Fish Audio fails — speak via browser TTS fallback
    const text = msg.text as string;
    console.log("[JARVIS text-fallback]", text);
    if (text) {
      speakWithBrowserTts(text);
    } else {
      transition("idle");
    }
  } else if (type === "status") {
    const state = msg.state as string;
    if (state === "thinking" && currentState !== "thinking") {
      transition("thinking");
    } else if (state === "working") {
      // Task spawned — show thinking with a different label
      transition("thinking");
      statusEl.textContent = "working...";
    } else if (state === "speaking" && currentState !== "speaking") {
      // Server signalling it's about to send audio — pre-transition so mic pauses promptly
      transition("speaking");
    } else if (state === "idle") {
      // Only honor server-idle when we are NOT actively playing audio.
      // If we're in "speaking", the audioPlayer.onFinished callback drives the
      // idle transition — honoring this early would resume the mic mid-playback.
      if (currentState !== "speaking") {
        transition("idle");
      }
    }
  } else if (type === "task_spawned") {
    console.log("[task]", "spawned:", msg.task_id, msg.prompt);
  } else if (type === "task_complete") {
    console.log("[task]", "complete:", msg.task_id, msg.status, msg.summary);
  }
});

// ---------------------------------------------------------------------------
// Activation gate — must click before Chrome allows AudioContext + mic
// ---------------------------------------------------------------------------

const overlay = document.getElementById("activation-overlay")!;

async function activate() {
  // 1. Resume AudioContext — MUST happen inside a user-gesture handler
  const ctx = audioPlayer.getAnalyser().context as AudioContext;
  try {
    await ctx.resume();
    console.log("[audio] context state after resume:", ctx.state);
  } catch (e) {
    console.warn("[audio] context resume failed:", e);
  }

  // 2. Fade out and remove overlay
  overlay.classList.add("hidden");
  setTimeout(() => overlay.remove(), 650);

  // 3. Now it's safe to start the mic
  voiceInput.start();
  transition("listening");
}

overlay.addEventListener("click", activate, { once: true });

// ---------------------------------------------------------------------------
// UI Controls
// ---------------------------------------------------------------------------

const btnMute = document.getElementById("btn-mute")!;
const btnMenu = document.getElementById("btn-menu")!;
const menuDropdown = document.getElementById("menu-dropdown")!;
const btnRestart = document.getElementById("btn-restart")!;
const btnFixSelf = document.getElementById("btn-fix-self")!;

btnMute.addEventListener("click", (e) => {
  e.stopPropagation();
  isMuted = !isMuted;
  btnMute.classList.toggle("muted", isMuted);
  if (isMuted) {
    voiceInput.pause();
    transition("idle");
  } else {
    voiceInput.resume();
    transition("listening");
  }
});

btnMenu.addEventListener("click", (e) => {
  e.stopPropagation();
  menuDropdown.style.display = menuDropdown.style.display === "none" ? "block" : "none";
});

document.addEventListener("click", () => {
  menuDropdown.style.display = "none";
});

btnRestart.addEventListener("click", async (e) => {
  e.stopPropagation();
  menuDropdown.style.display = "none";
  statusEl.textContent = "restarting...";
  try {
    await fetch("/api/restart", { method: "POST" });
    // Wait a few seconds then reload
    setTimeout(() => window.location.reload(), 4000);
  } catch {
    statusEl.textContent = "restart failed";
  }
});

btnFixSelf.addEventListener("click", (e) => {
  e.stopPropagation();
  menuDropdown.style.display = "none";
  // Activate work mode on the WebSocket session (JARVIS becomes Claude Code's voice)
  socket.send({ type: "fix_self" });
  statusEl.textContent = "entering work mode...";
});

// Settings button
const btnSettings = document.getElementById("btn-settings")!;
btnSettings.addEventListener("click", (e) => {
  e.stopPropagation();
  menuDropdown.style.display = "none";
  openSettings();
});

// First-time setup detection — check after a short delay for server readiness
setTimeout(() => {
  checkFirstTimeSetup();
}, 2000);
