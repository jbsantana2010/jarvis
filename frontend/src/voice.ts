/**
 * Voice input (Web Speech API) and audio output (AudioContext) for JARVIS.
 */

// ---------------------------------------------------------------------------
// Speech Recognition
// ---------------------------------------------------------------------------

export interface VoiceInput {
  start(): void;
  stop(): void;
  pause(): void;
  resume(): void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const webkitSpeechRecognition: any;

export function createVoiceInput(
  onTranscript: (text: string) => void,
  onError: (msg: string) => void
): VoiceInput {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const SR = (window as any).SpeechRecognition || (typeof webkitSpeechRecognition !== "undefined" ? webkitSpeechRecognition : null);
  if (!SR) {
    onError("Speech recognition not supported in this browser");
    return { start() {}, stop() {}, pause() {}, resume() {} };
  }

  const recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  let shouldListen = false;
  let paused = false;
  // Activity tracker: any onstart/onresult/onend/onerror updates this.
  // The heartbeat below uses it to detect a wedged recognition session
  // (Chrome's Web Speech API can go silent after audio output or long
  // idle periods without firing the obvious error handlers).
  let lastActivityTs = Date.now();
  let heartbeat: ReturnType<typeof setInterval> | null = null;
  const HEARTBEAT_INTERVAL_MS = 4000;
  const STALE_AFTER_MS = 12000;

  function safeStart(): void {
    try {
      recognition.start();
    } catch {
      // Already started — fine
    }
  }

  function forceRestart(reason: string): void {
    console.log("[voice] forceRestart:", reason);
    try { recognition.abort(); } catch { /* ignore */ }
    setTimeout(() => {
      if (shouldListen && !paused) safeStart();
    }, 200);
  }

  function ensureHeartbeat(): void {
    if (heartbeat !== null) return;
    heartbeat = setInterval(() => {
      if (!shouldListen || paused) return;
      const idle = Date.now() - lastActivityTs;
      if (idle > STALE_AFTER_MS) {
        forceRestart(`stale ${idle}ms`);
        lastActivityTs = Date.now();  // avoid immediate re-fire
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  function clearHeartbeat(): void {
    if (heartbeat !== null) {
      clearInterval(heartbeat);
      heartbeat = null;
    }
  }

  recognition.onstart = () => {
    lastActivityTs = Date.now();
    console.log("[voice] onstart");
  };

  recognition.onresult = (event: any) => {
    lastActivityTs = Date.now();
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        const text = event.results[i][0].transcript.trim();
        if (text) onTranscript(text);
      }
    }
  };

  recognition.onend = () => {
    lastActivityTs = Date.now();
    console.log(`[voice] onend (shouldListen=${shouldListen}, paused=${paused})`);
    if (shouldListen && !paused) {
      safeStart();
    }
  };

  recognition.onerror = (event: any) => {
    lastActivityTs = Date.now();
    if (event.error === "not-allowed") {
      onError("Microphone access denied. Please allow microphone access.");
      shouldListen = false;
      clearHeartbeat();
    } else if (event.error === "no-speech") {
      // Normal idle — onend will restart
      console.log("[voice] no-speech");
    } else if (event.error === "aborted") {
      // Expected during pause / forceRestart
    } else if (event.error === "audio-capture") {
      onError("No microphone detected. Check your input device.");
      console.warn("[voice] audio-capture error");
    } else if (event.error === "network") {
      console.warn("[voice] network error — Web Speech API needs internet");
    } else {
      console.warn("[voice] recognition error:", event.error);
    }
  };

  return {
    start() {
      shouldListen = true;
      paused = false;
      lastActivityTs = Date.now();
      safeStart();
      ensureHeartbeat();
    },
    stop() {
      shouldListen = false;
      paused = false;
      clearHeartbeat();
      try { recognition.stop(); } catch { /* ignore */ }
    },
    pause() {
      paused = true;
      try { recognition.stop(); } catch { /* ignore */ }
    },
    resume() {
      paused = false;
      lastActivityTs = Date.now();
      if (shouldListen) {
        safeStart();
        ensureHeartbeat();
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Audio Player
// ---------------------------------------------------------------------------

export interface AudioPlayer {
  enqueue(base64: string): Promise<void>;
  stop(): void;
  getAnalyser(): AnalyserNode;
  onFinished(cb: () => void): void;
}

export function createAudioPlayer(): AudioPlayer {
  const audioCtx = new AudioContext();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = 0.8;
  analyser.connect(audioCtx.destination);

  const queue: AudioBuffer[] = [];
  let isPlaying = false;
  let currentSource: AudioBufferSourceNode | null = null;
  let finishedCallback: (() => void) | null = null;

  function playNext() {
    if (queue.length === 0) {
      isPlaying = false;
      currentSource = null;
      finishedCallback?.();
      return;
    }

    isPlaying = true;
    const buffer = queue.shift()!;
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    currentSource = source;

    source.onended = () => {
      if (currentSource === source) {
        playNext();
      }
    };

    source.start();
  }

  return {
    async enqueue(base64: string) {
      // Resume audio context (browser autoplay policy)
      if (audioCtx.state === "suspended") {
        await audioCtx.resume();
      }

      try {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        const audioBuffer = await audioCtx.decodeAudioData(bytes.buffer.slice(0));
        queue.push(audioBuffer);
        if (!isPlaying) playNext();
      } catch (err) {
        console.error("[audio] decode error:", err);
        if (!isPlaying) {
          if (queue.length > 0) {
            playNext();
          } else {
            // Nothing queued or playing — unblock the state machine
            finishedCallback?.();
          }
        }
      }
    },

    stop() {
      queue.length = 0;
      if (currentSource) {
        try {
          currentSource.stop();
        } catch {
          // Already stopped
        }
        currentSource = null;
      }
      isPlaying = false;
    },

    getAnalyser() {
      return analyser;
    },

    onFinished(cb: () => void) {
      finishedCallback = cb;
    },
  };
}
