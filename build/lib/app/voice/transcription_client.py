from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings
from app.observability.metrics import VOICE_STT_DURATION, enabled as metrics_enabled
from app.observability.tracing import tracer
from app.voice.mulaw import mulaw_to_wav


class VoiceTranscriptionError(RuntimeError):
    pass


@dataclass(slots=True)
class VoiceTranscriptionResult:
    text: str
    model: str
    audio_bytes: int


class OpenAITranscriptionClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise VoiceTranscriptionError("OPENAI_API_KEY nao configurada")

    async def transcribe_mulaw(self, audio: bytes) -> VoiceTranscriptionResult:
        started = time.perf_counter()
        try:
            with tracer("app.voice").start_as_current_span("voice.stt") as span:
                span.set_attribute("gen_ai.request.model", settings.openai_transcribe_model)
                span.set_attribute("audio.input.bytes", len(audio))
                result = await asyncio.to_thread(self._transcribe_sync, audio)
                span.set_attribute("audio.transcript.chars", len(result.text))
                return result
        finally:
            if metrics_enabled():
                VOICE_STT_DURATION.labels(settings.openai_transcribe_model).observe(
                    max(0.0, time.perf_counter() - started)
                )

    def _transcribe_sync(self, audio: bytes) -> VoiceTranscriptionResult:
        if not audio:
            raise VoiceTranscriptionError("Audio vazio para transcricao")
        wav_bytes = mulaw_to_wav(audio)
        client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        response = client.audio.transcriptions.create(
            model=settings.openai_transcribe_model,
            file=("twilio-utterance.wav", wav_bytes, "audio/wav"),
            language="pt",
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise VoiceTranscriptionError("Transcricao retornou texto vazio")
        return VoiceTranscriptionResult(
            text=text,
            model=settings.openai_transcribe_model,
            audio_bytes=len(audio),
        )
