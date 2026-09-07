from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import websocket

from app.core.config import settings
from app.observability.metrics import VOICE_REALTIME_DURATION, enabled as metrics_enabled
from app.observability.tracing import tracer


class RealtimeVoiceError(RuntimeError):
    pass


@dataclass(slots=True)
class RealtimeTextResult:
    session_id: str | None
    response_id: str | None
    text: str
    event_count: int
    latency_ms: int
    usage: dict[str, Any]


@dataclass(slots=True)
class RealtimeAudioResult:
    session_id: str | None
    response_id: str | None
    transcript: str
    audio_bytes: int
    audio_sha256: str
    event_count: int
    latency_ms: int
    usage: dict[str, Any]
    audio_data: bytes


class OpenAIRealtimeClient:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RealtimeVoiceError("OPENAI_API_KEY is not configured")

    @staticmethod
    def _safety_identifier(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    def _connect(self, *, safety_identifier: str):
        url = f"wss://api.openai.com/v1/realtime?model={settings.openai_realtime_model}"
        headers = [
            "Authorization: Bearer " + str(settings.openai_api_key),
            "OpenAI-Safety-Identifier: " + self._safety_identifier(safety_identifier),
        ]
        return websocket.create_connection(
            url,
            header=headers,
            timeout=settings.openai_realtime_timeout_seconds,
            enable_multithread=True,
        )

    @staticmethod
    def _recv_json(ws) -> dict[str, Any]:
        raw = ws.recv()
        if not raw:
            raise RealtimeVoiceError("Realtime WebSocket closed before response completed")
        event = json.loads(raw)
        if event.get("type") == "error":
            error = event.get("error") or {}
            raise RealtimeVoiceError(str(error.get("message") or event))
        return event

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(str(content["text"]))
        return "".join(parts).strip()

    @staticmethod
    def _response_audio_transcript(response: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in response.get("output") or []:
            for content in item.get("content") or []:
                transcript = content.get("transcript")
                if transcript:
                    parts.append(str(transcript))
        return "".join(parts).strip()

    def _wait_session(self, ws) -> tuple[str | None, int]:
        count = 0
        while True:
            event = self._recv_json(ws); count += 1
            if event.get("type") == "session.created":
                session = event.get("session") or {}
                return session.get("id"), count

    async def text_probe(self, *, message: str, safety_identifier: str) -> RealtimeTextResult:
        with tracer("app.voice").start_as_current_span("voice.realtime.text") as span:
            span.set_attribute("gen_ai.request.model", settings.openai_realtime_model)
            result = await asyncio.to_thread(self._text_probe_sync, message, safety_identifier)
            span.set_attribute("gen_ai.response.id", result.response_id or "")
            if metrics_enabled():
                VOICE_REALTIME_DURATION.labels(settings.openai_realtime_model, "text").observe(
                    max(0.0, result.latency_ms / 1000)
                )
            return result

    def _text_probe_sync(self, message: str, safety_identifier: str) -> RealtimeTextResult:
        started = time.perf_counter()
        ws = self._connect(safety_identifier=safety_identifier)
        try:
            session_id, event_count = self._wait_session(ws)
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "output_modalities": ["text"],
                    "instructions": "Responda em português do Brasil, de forma extremamente curta e literal.",
                },
            }))
            ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": message}],
                },
            }))
            ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": ["text"]}}))
            pieces: list[str] = []
            response_id = None
            usage: dict[str, Any] = {}
            while True:
                event = self._recv_json(ws); event_count += 1
                typ = event.get("type")
                if typ == "response.output_text.delta":
                    pieces.append(str(event.get("delta") or ""))
                elif typ == "response.done":
                    response = event.get("response") or {}
                    response_id = response.get("id")
                    usage = response.get("usage") or {}
                    if not pieces:
                        fallback = self._response_text(response)
                        if fallback:
                            pieces.append(fallback)
                    break
            return RealtimeTextResult(
                session_id=session_id,
                response_id=response_id,
                text="".join(pieces).strip(),
                event_count=event_count,
                latency_ms=int((time.perf_counter()-started)*1000),
                usage=usage,
            )
        finally:
            try: ws.close()
            except Exception: pass

    async def render_text_audio(self, *, text: str, safety_identifier: str) -> RealtimeAudioResult:
        with tracer("app.voice").start_as_current_span("voice.realtime.audio") as span:
            span.set_attribute("gen_ai.request.model", settings.openai_realtime_model)
            result = await asyncio.to_thread(self._render_text_audio_sync, text, safety_identifier)
            span.set_attribute("gen_ai.response.id", result.response_id or "")
            span.set_attribute("audio.output.bytes", result.audio_bytes)
            if metrics_enabled():
                VOICE_REALTIME_DURATION.labels(settings.openai_realtime_model, "audio").observe(
                    max(0.0, result.latency_ms / 1000)
                )
            return result

    def _render_text_audio_sync(self, text: str, safety_identifier: str) -> RealtimeAudioResult:
        started = time.perf_counter()
        ws = self._connect(safety_identifier=safety_identifier)
        audio = bytearray()
        transcript_parts: list[str] = []
        try:
            session_id, event_count = self._wait_session(ws)
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "output_modalities": ["audio"],
                    "audio": {
                        "output": {
                            "format": {"type": "audio/pcmu"},
                            "voice": settings.openai_realtime_voice,
                        }
                    },
                    "instructions": "Fale em português do Brasil com clareza. Não acrescente informações ao texto solicitado.",
                },
            }))
            ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "Leia exatamente a resposta abaixo, sem comentários extras:\n" + text,
                    }],
                },
            }))
            ws.send(json.dumps({"type": "response.create", "response": {"output_modalities": ["audio"]}}))
            response_id = None
            usage: dict[str, Any] = {}
            while True:
                event = self._recv_json(ws); event_count += 1
                typ = event.get("type")
                if typ == "response.output_audio.delta":
                    chunk = base64.b64decode(str(event.get("delta") or ""))
                    audio.extend(chunk)
                    if len(audio) > settings.voice_audio_max_bytes:
                        raise RealtimeVoiceError("Realtime audio exceeded VOICE_AUDIO_MAX_BYTES")
                elif typ == "response.output_audio_transcript.delta":
                    transcript_parts.append(str(event.get("delta") or ""))
                elif typ == "response.done":
                    response = event.get("response") or {}
                    response_id = response.get("id")
                    usage = response.get("usage") or {}
                    if not transcript_parts:
                        fallback = self._response_audio_transcript(response)
                        if fallback:
                            transcript_parts.append(fallback)
                    break
            if not audio:
                raise RealtimeVoiceError("Realtime response completed without audio bytes")
            raw = bytes(audio)
            return RealtimeAudioResult(
                session_id=session_id,
                response_id=response_id,
                transcript="".join(transcript_parts).strip(),
                audio_bytes=len(raw),
                audio_sha256=hashlib.sha256(raw).hexdigest(),
                event_count=event_count,
                latency_ms=int((time.perf_counter()-started)*1000),
                usage=usage,
                audio_data=raw,
            )
        finally:
            try: ws.close()
            except Exception: pass
