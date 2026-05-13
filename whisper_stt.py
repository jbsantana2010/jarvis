"""
whisper_stt.py — Server-side speech-to-text via faster-whisper (Sprint 18).

Replaces the browser Web Speech API for consistent cross-machine transcription.
Model: tiny (39M params, ~75 MB quantised, <1 s inference on CPU for 3 s audio).

Public API:
    preload()                                   — call at server start to warm model
    transcribe_bytes(audio_bytes, suffix) -> str — sync
    transcribe_async(audio_bytes, suffix) -> str — async (runs in executor)
    is_available() -> bool
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Optional

log = logging.getLogger("jarvis.whisper_stt")

MODEL_SIZE: str = os.getenv("WHISPER_MODEL", "tiny")
_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model
    from faster_whisper import WhisperModel
    log.info("[whisper] loading model '%s' …", MODEL_SIZE)
    _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    log.info("[whisper] model '%s' ready", MODEL_SIZE)
    return _model


def preload() -> None:
    """Eagerly load the model at server start so the first request is fast."""
    try:
        _load_model()
    except Exception as e:
        log.warning("[whisper] preload failed (STT will be unavailable): %s", e)


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """Synchronous transcription. Returns text string (empty if nothing heard)."""
    model = _load_model()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        segments, info = model.transcribe(
            tmp,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            language="en",
        )
        text = " ".join(s.text.strip() for s in segments if s.text.strip())
        log.debug("[whisper] %.1fs audio → %r", info.duration, text[:80])
        return text.strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


async def transcribe_async(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """Async wrapper — runs transcription in a thread to avoid blocking the loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, transcribe_bytes, audio_bytes, suffix)
