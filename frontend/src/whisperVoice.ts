/**
 * whisperVoice.ts — Server-side Whisper ASR voice input (Sprint 18)
 *
 * Implements the same VoiceInput interface as createVoiceInput() in voice.ts
 * but routes audio through faster-whisper on the backend instead of the
 * browser's Web Speech API.
 *
 * Flow:
 *   1. getUserMedia() → raw microphone stream
 *   2. AudioContext AnalyserNode → RMS VAD (energy threshold)
 *   3. VAD speech start → MediaRecorder.start()
 *   4. VAD silence > SILENCE_MS → MediaRecorder.stop() → blob collected
 *   5. POST blob as multipart to /api/stt/transcribe → text
 *   6. onTranscript(text) called — same as browser STT path
 */

import type { VoiceInput } from "./voice";

// ---------------------------------------------------------------------------
// Tuning constants
// ---------------------------------------------------------------------------

/** RMS energy (0–1) above which we consider the mic "active" */
const VAD_THRESHOLD = 0.012;

/** How long silence must persist (ms) before we close an utterance */
const SILENCE_MS = 700;

/** Minimum utterance duration (ms) — ignore blips shorter than this */
const MIN_SPEECH_MS = 200;

/** VAD poll interval (ms) */
const VAD_POLL_MS = 40;

/** Audio MIME type — webm/opus preferred, fallback to whatever browser supports */
function pickMime(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

// ---------------------------------------------------------------------------
// Public factory
// ---------------------------------------------------------------------------

export async function createWhisperVoiceInput(
  onTranscript: (text: string) => void,
  onError: (msg: string) => void
): Promise<VoiceInput> {

  // Acquire mic stream once — reused across all utterances
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (err) {
    onError("Microphone access denied. Please allow microphone access.");
    console.error("[whisper] getUserMedia failed:", err);
    // Return a no-op VoiceInput so the rest of the app doesn't crash
    return { start() {}, stop() {}, pause() {}, resume() {} };
  }

  const mime = pickMime();
  const audioCtx = new AudioContext();
  const source = audioCtx.createMediaStreamSource(stream);
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.4;
  source.connect(analyser);

  const fftBuf = new Uint8Array(analyser.fftSize);

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  let shouldListen = false;
  let paused = false;

  // VAD / recording state
  let speaking = false;
  let silenceStart = 0;
  let speechStart = 0;
  let recorder: MediaRecorder | null = null;
  let chunks: Blob[] = [];
  let vadTimer: ReturnType<typeof setInterval> | null = null;

  // -------------------------------------------------------------------------
  // VAD helper
  // -------------------------------------------------------------------------
  function rms(): number {
    analyser.getByteTimeDomainData(fftBuf);
    let sum = 0;
    for (let i = 0; i < fftBuf.length; i++) {
      const v = (fftBuf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / fftBuf.length);
  }

  // -------------------------------------------------------------------------
  // Recording helpers
  // -------------------------------------------------------------------------
  function startRecording(): void {
    chunks = [];
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch {
      recorder = new MediaRecorder(stream);
    }
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    recorder.onstop = () => {
      void sendChunks();
    };
    recorder.start(100); // collect in 100 ms slices
    console.log("[whisper] recording started, mime:", recorder.mimeType);
  }

  function stopRecording(): void {
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    recorder = null;
  }

  async function sendChunks(): Promise<void> {
    if (chunks.length === 0) return;

    const actualMime = recorder?.mimeType ?? mime;
    const ext = actualMime.includes("ogg") ? ".ogg" : actualMime.includes("mp4") ? ".mp4" : ".webm";
    const blob = new Blob(chunks, { type: actualMime });
    chunks = [];

    if (blob.size < 1000) {
      // Too small — likely just noise
      console.log("[whisper] blob too small, skipping:", blob.size);
      return;
    }

    console.log("[whisper] posting", blob.size, "bytes to /api/stt/transcribe");

    const form = new FormData();
    form.append("audio", blob, `utterance${ext}`);

    try {
      const res = await fetch("/api/stt/transcribe", { method: "POST", body: form });
      if (!res.ok) {
        console.warn("[whisper] transcribe HTTP", res.status);
        return;
      }
      const data = await res.json() as { text?: string; error?: string };
      if (data.error) {
        console.warn("[whisper] transcribe error:", data.error);
        return;
      }
      const text = (data.text ?? "").trim();
      console.log("[whisper] transcript:", text);
      if (text) onTranscript(text);
    } catch (err) {
      console.error("[whisper] fetch failed:", err);
      onError("Whisper transcription failed — check server logs.");
    }
  }

  // -------------------------------------------------------------------------
  // VAD loop
  // -------------------------------------------------------------------------
  function startVad(): void {
    if (vadTimer !== null) return;
    vadTimer = setInterval(() => {
      if (!shouldListen || paused) return;

      const energy = rms();

      if (!speaking) {
        if (energy > VAD_THRESHOLD) {
          speaking = true;
          speechStart = Date.now();
          silenceStart = 0;
          startRecording();
          console.log("[whisper] speech start (rms:", energy.toFixed(4), ")");
        }
      } else {
        if (energy < VAD_THRESHOLD) {
          if (silenceStart === 0) silenceStart = Date.now();
          const silenceDuration = Date.now() - silenceStart;
          if (silenceDuration >= SILENCE_MS) {
            const speechDuration = Date.now() - speechStart;
            speaking = false;
            silenceStart = 0;
            if (speechDuration >= MIN_SPEECH_MS) {
              console.log("[whisper] speech end, duration:", speechDuration, "ms");
              stopRecording(); // triggers onstop → sendChunks
            } else {
              // Too short — discard
              if (recorder && recorder.state !== "inactive") {
                recorder.ondataavailable = null;
                recorder.onstop = null;
                recorder.stop();
              }
              recorder = null;
              chunks = [];
              console.log("[whisper] utterance too short, discarded");
            }
          }
        } else {
          // Energy back up — reset silence timer
          silenceStart = 0;
        }
      }
    }, VAD_POLL_MS);
  }

  function stopVad(): void {
    if (vadTimer !== null) {
      clearInterval(vadTimer);
      vadTimer = null;
    }
  }

  // -------------------------------------------------------------------------
  // VoiceInput interface
  // -------------------------------------------------------------------------
  return {
    start() {
      shouldListen = true;
      paused = false;
      if (audioCtx.state === "suspended") void audioCtx.resume();
      startVad();
      console.log("[whisper] voice input started");
    },

    stop() {
      shouldListen = false;
      paused = false;
      stopVad();
      stopRecording();
      // Release mic tracks
      stream.getTracks().forEach((t) => t.stop());
      void audioCtx.close();
      console.log("[whisper] voice input stopped");
    },

    pause() {
      paused = true;
      // If mid-utterance, stop and discard (mic is paused while JARVIS speaks)
      if (speaking && recorder) {
        speaking = false;
        silenceStart = 0;
        if (recorder.state !== "inactive") {
          recorder.ondataavailable = null;
          recorder.onstop = null;
          recorder.stop();
        }
        recorder = null;
        chunks = [];
      }
      console.log("[whisper] paused");
    },

    resume() {
      paused = false;
      if (shouldListen) {
        if (audioCtx.state === "suspended") void audioCtx.resume();
        startVad();
      }
      console.log("[whisper] resumed");
    },
  };
}
