from __future__ import annotations

import asyncio
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings
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
        return await asyncio.to_thread(self._transcribe_sync, audio)

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
