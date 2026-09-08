from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass

from fastapi import WebSocket
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.channel import ChannelAccount
from app.models.user import User
from app.models.voice import VoiceEvent, VoiceSession
from app.observability.context import bind_context, clear_context
from app.observability.metrics import ACTIVE_VOICE_SESSIONS, TWILIO_CALL_ERRORS, enabled as metrics_enabled
from app.observability.tracing import tracer
from app.services.voice_service import VoiceService
from app.voice.mulaw import mulaw_rms
from app.voice.transcription_client import OpenAITranscriptionClient
from app.voice.twilio_protocol import (
    TWILIO_MEDIA_FRAME_MS,
    build_clear_message,
    build_mark_message,
    build_media_message,
    iter_mulaw_frames,
    parse_media_message,
    parse_start_message,
)
from app.voice.twilio_security import TwilioSecurityError, validate_websocket_signature

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BridgeMetrics:
    inbound_frames: int = 0
    inbound_bytes: int = 0
    outbound_frames: int = 0
    outbound_bytes: int = 0
    marks_sent: int = 0
    marks_received: int = 0
    clears_sent: int = 0
    barge_in_count: int = 0
    transcription_turns: int = 0
    transcription_audio_bytes: int = 0
    vad_speech_frames: int = 0
    vad_silence_frames: int = 0


class TwilioMediaBridge:
    """Ponte Twilio Media Streams.

    mode="lab" preserva o comportamento deterministico validado na v0.10.
    mode="production" exige assinatura Twilio no handshake, remove a injecao de
    transcript e detecta o primeiro turno de voz a partir de audio mu-law real.

    A v0.11 limita deliberadamente o caminho de STT de producao ao primeiro
    turno por chamada. A sessao de voz e o canal continuam auditados, e a
    evolucao multi-turn streaming fica explicitamente para a proxima fase.
    """

    def __init__(
        self,
        websocket: WebSocket,
        *,
        mode: str = "lab",
        provider_account_id: str | None = None,
    ) -> None:
        self.websocket = websocket
        self.mode = mode
        self.provider_account_id = provider_account_id or ""
        self.metrics = BridgeMetrics()
        self.stream_sid = ""
        self.call_sid = ""
        self.from_address = ""
        self.session_id = None
        self.output_active = False
        self.output_cancelled = asyncio.Event()
        self.send_lock = asyncio.Lock()
        self.output_task: asyncio.Task | None = None
        self.input_task: asyncio.Task | None = None
        self.account: ChannelAccount | None = None
        self.runtime_user: User | None = None
        self.utterance_audio = bytearray()
        self.speech_started = False
        self.speech_ms = 0
        self.silence_ms = 0
        self.production_turn_started = False
        self.last_transcript = ""

    async def _send_json(self, payload: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def _load_account_and_user(self, provider_account_id: str) -> tuple[ChannelAccount, User]:
        async with AsyncSessionLocal() as db:
            account = (
                await db.execute(
                    select(ChannelAccount).where(
                        ChannelAccount.channel == "voice",
                        ChannelAccount.provider == "twilio",
                        ChannelAccount.provider_account_id == provider_account_id,
                        ChannelAccount.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                raise RuntimeError("Conta de canal Voice/Twilio nao encontrada")
            user = (
                await db.execute(
                    select(User).where(
                        User.id == account.runtime_user_id,
                        User.tenant_id == account.tenant_id,
                        User.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if user is None:
                raise RuntimeError("Usuario de runtime do canal Voice indisponivel")
            return account, user

    async def _persist_bridge_summary(self, *, interrupted: bool) -> None:
        if self.session_id is None:
            return
        async with AsyncSessionLocal() as db:
            session = (
                await db.execute(select(VoiceSession).where(VoiceSession.id == self.session_id))
            ).scalar_one_or_none()
            if session is None:
                return
            metadata = dict(session.session_metadata or {})
            metadata["twilio_bridge"] = {
                **asdict(self.metrics),
                "stream_sid": self.stream_sid,
                "call_sid": self.call_sid,
                "interrupted": interrupted,
                "frame_ms": TWILIO_MEDIA_FRAME_MS,
                "mode": self.mode,
                "production_first_turn_only": settings.voice_production_first_turn_only,
                "last_transcript": self.last_transcript,
                "transcribe_model": settings.openai_transcribe_model if self.mode == "production" else None,
            }
            session.session_metadata = metadata
            db.add(
                VoiceEvent(
                    tenant_id=session.tenant_id,
                    voice_session_id=session.id,
                    direction="system",
                    event_type="twilio_media_stream",
                    status="completed",
                    audio_bytes=self.metrics.inbound_bytes + self.metrics.outbound_bytes,
                    event_metadata=metadata["twilio_bridge"],
                )
            )
            await db.commit()

    async def _produce_business_audio(
        self,
        *,
        account: ChannelAccount,
        runtime_user: User,
        from_address: str,
        transcript: str,
        event_source: str,
    ) -> None:
        interrupted = False
        try:
            async with AsyncSessionLocal() as db:
                result = await VoiceService().bridge_turn(
                    db=db,
                    current_user=runtime_user,
                    account=account,
                    provider_call_id=self.call_sid,
                    from_address=from_address,
                    transcript=transcript,
                    event_source=event_source,
                )
            self.session_id = result.session.id
            if result.deduplicated or not result.audio_data:
                return

            frames = list(iter_mulaw_frames(result.audio_data))
            if not frames:
                return
            self.output_active = True
            sleep_seconds = max(
                0.0,
                TWILIO_MEDIA_FRAME_MS / 1000 / settings.voice_bridge_playback_speed,
            )
            for frame in frames:
                if self.output_cancelled.is_set():
                    interrupted = True
                    break
                await self._send_json(build_media_message(stream_sid=self.stream_sid, audio=frame))
                self.metrics.outbound_frames += 1
                self.metrics.outbound_bytes += len(frame)
                if sleep_seconds:
                    await asyncio.sleep(sleep_seconds)
            self.output_active = False
            if not interrupted:
                mark_name = f"assistant-{str(self.session_id)[:8]}"
                await self._send_json(build_mark_message(stream_sid=self.stream_sid, name=mark_name))
                self.metrics.marks_sent += 1
        except asyncio.CancelledError:
            interrupted = True
            raise
        except Exception:
            logger.exception("Falha no turno de negocio da ponte Twilio")
            raise
        finally:
            self.output_active = False

    def _reset_utterance(self) -> bytes:
        raw = bytes(self.utterance_audio)
        self.utterance_audio.clear()
        self.speech_started = False
        self.speech_ms = 0
        self.silence_ms = 0
        return raw

    async def _process_production_utterance(self, audio: bytes) -> None:
        try:
            with tracer("app.voice").start_as_current_span("voice.twilio.turn") as span:
                span.set_attribute("voice.mode", self.mode)
                span.set_attribute("audio.input.bytes", len(audio))
                if self.call_sid:
                    span.set_attribute("twilio.call_sid", self.call_sid)
                result = await OpenAITranscriptionClient().transcribe_mulaw(audio)
                transcript = result.text.strip()
                self.last_transcript = transcript
                self.metrics.transcription_turns += 1
                self.metrics.transcription_audio_bytes += len(audio)
                if not transcript:
                    return
                if self.account is None or self.runtime_user is None:
                    raise RuntimeError("Contexto Twilio de producao nao carregado")
                await self._produce_business_audio(
                    account=self.account,
                    runtime_user=self.runtime_user,
                    from_address=self.from_address,
                    transcript=transcript,
                    event_source="twilio_media_stream_production_stt",
                )
        except Exception:
            logger.exception("Falha ao transcrever/processar audio Twilio de producao")
            raise

    def _consume_production_audio(self, audio: bytes) -> bytes | None:
        if settings.voice_production_first_turn_only and self.production_turn_started:
            return None
        rms = mulaw_rms(audio)
        is_speech = rms >= settings.voice_vad_rms_threshold
        if is_speech:
            self.metrics.vad_speech_frames += 1
            self.speech_started = True
            self.speech_ms += TWILIO_MEDIA_FRAME_MS
            self.silence_ms = 0
            self.utterance_audio.extend(audio)
        elif self.speech_started:
            self.metrics.vad_silence_frames += 1
            self.silence_ms += TWILIO_MEDIA_FRAME_MS
            self.utterance_audio.extend(audio)

        if not self.speech_started:
            return None
        if self.speech_ms + self.silence_ms >= settings.voice_vad_max_utterance_ms:
            self.production_turn_started = True
            return self._reset_utterance()
        if self.silence_ms >= settings.voice_vad_silence_ms:
            if self.speech_ms < settings.voice_vad_min_speech_ms:
                self._reset_utterance()
                return None
            self.production_turn_started = True
            return self._reset_utterance()
        return None

    async def _prepare_production_handshake(self) -> None:
        if not settings.voice_production_enabled:
            raise RuntimeError("VOICE_PRODUCTION_ENABLED esta desabilitado")
        if not self.provider_account_id:
            raise RuntimeError("provider_account_id obrigatorio no endpoint de producao")
        self.account, self.runtime_user = await self._load_account_and_user(self.provider_account_id)
        bind_context(tenant_id=str(self.account.tenant_id))
        if self.account.outbound_mode != "twilio_media_stream":
            raise RuntimeError("Conta Voice nao esta em modo twilio_media_stream")
        if not validate_websocket_signature(websocket=self.websocket, account=self.account):
            raise TwilioSecurityError("Assinatura X-Twilio-Signature invalida no handshake WSS")

    async def run(self) -> None:
        try:
            if self.mode == "production":
                await self._prepare_production_handshake()
            elif not settings.voice_bridge_lab_enabled:
                raise RuntimeError("Modo de laboratorio da ponte Voice esta desabilitado")
        except Exception as exc:
            logger.warning("Handshake Twilio rejeitado: %s", exc)
            if metrics_enabled():
                TWILIO_CALL_ERRORS.labels("websocket-handshake").inc()
            try:
                await self.websocket.close(code=1008, reason=str(exc)[:120])
            except Exception:
                pass
            return

        await self.websocket.accept()
        if metrics_enabled():
            ACTIVE_VOICE_SESSIONS.labels(self.mode).inc()
        try:
            while True:
                payload = await self.websocket.receive_json()
                parsed = parse_media_message(payload)
                event = parsed["event"]

                if event == "connected":
                    continue

                if event == "start":
                    start = parse_start_message(payload)
                    self.stream_sid = start["stream_sid"]
                    self.call_sid = start["call_sid"]
                    bind_context(call_sid=self.call_sid)
                    params = start["custom_parameters"]
                    if self.mode == "production":
                        assert self.account is not None
                        configured_sid = str(self.account.business_account_id or "").strip()
                        received_sid = str(start["account_sid"] or "").strip()
                        if not configured_sid:
                            raise RuntimeError("Conta Twilio sem AccountSid configurado")
                        if not received_sid:
                            raise RuntimeError("Twilio production start requer AccountSid")
                        if configured_sid != received_sid:
                            raise RuntimeError("AccountSid do start nao corresponde a conta configurada")
                        self.from_address = str(params.get("from_address") or "")
                        if not self.from_address:
                            raise RuntimeError("Twilio production start requer customParameter from_address")
                    else:
                        provider_account_id = str(params.get("provider_account_id") or "")
                        lab_token = str(params.get("lab_token") or "")
                        self.from_address = str(params.get("from_address") or "")
                        transcript = str(params.get("lab_transcript") or "")
                        if not provider_account_id or not self.from_address:
                            raise RuntimeError("Twilio lab start requer provider_account_id e from_address")
                        if lab_token != settings.voice_bridge_lab_token:
                            raise RuntimeError("Token de laboratorio Voice invalido")
                        if not transcript:
                            raise RuntimeError("Modo lab requer lab_transcript")
                        account, runtime_user = await self._load_account_and_user(provider_account_id)
                        self.output_task = asyncio.create_task(
                            self._produce_business_audio(
                                account=account,
                                runtime_user=runtime_user,
                                from_address=self.from_address,
                                transcript=transcript,
                                event_source="twilio_media_stream_lab",
                            )
                        )
                    continue

                if event == "media":
                    self.metrics.inbound_frames += 1
                    self.metrics.inbound_bytes += int(parsed["audio_bytes"])
                    if (
                        self.output_active
                        and settings.voice_barge_in_enabled
                        and not self.output_cancelled.is_set()
                    ):
                        self.output_cancelled.set()
                        self.metrics.barge_in_count += 1
                        await self._send_json(build_clear_message(stream_sid=self.stream_sid))
                        self.metrics.clears_sent += 1
                    if self.mode == "production":
                        utterance = self._consume_production_audio(parsed["audio"])
                        if utterance and self.input_task is None:
                            self.input_task = asyncio.create_task(self._process_production_utterance(utterance))
                    continue

                if event == "mark":
                    self.metrics.marks_received += 1
                    continue

                if event == "dtmf":
                    continue

                if event == "stop":
                    if self.mode == "production" and self.speech_started and not self.production_turn_started:
                        pending_speech_ms = self.speech_ms
                        pending = self._reset_utterance()
                        if pending and pending_speech_ms >= settings.voice_vad_min_speech_ms:
                            self.production_turn_started = True
                            self.input_task = asyncio.create_task(self._process_production_utterance(pending))
                    break
        except Exception as exc:
            logger.warning("Ponte Twilio encerrada com erro: %s", exc)
            try:
                await self.websocket.close(code=1008, reason=str(exc)[:120])
            except Exception:
                pass
        finally:
            if metrics_enabled():
                ACTIVE_VOICE_SESSIONS.labels(self.mode).dec()
            for task in (self.input_task, self.output_task):
                if task is not None:
                    try:
                        await asyncio.wait_for(task, timeout=settings.openai_realtime_timeout_seconds + 45)
                    except asyncio.TimeoutError:
                        task.cancel()
                    except Exception:
                        pass
            try:
                await self._persist_bridge_summary(interrupted=self.output_cancelled.is_set())
            except Exception:
                logger.exception("Falha ao persistir resumo da ponte Twilio")
            try:
                await self.websocket.close()
            except Exception:
                pass
            clear_context()
