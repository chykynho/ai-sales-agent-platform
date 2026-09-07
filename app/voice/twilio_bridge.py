from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, asdict

from fastapi import WebSocket
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.channel import ChannelAccount
from app.models.user import User
from app.models.voice import VoiceEvent, VoiceSession
from app.services.voice_service import VoiceService
from app.voice.twilio_protocol import (
    TWILIO_MEDIA_FRAME_MS,
    build_clear_message,
    build_mark_message,
    build_media_message,
    iter_mulaw_frames,
    parse_media_message,
    parse_start_message,
)

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


class TwilioMediaBridge:
    """v0.10 Twilio Media Streams bridge laboratory.

    The public WebSocket speaks the Twilio bidirectional Media Streams protocol.
    For deterministic local validation, a transcript is injected through a Twilio
    start.customParameters field. The business turn still runs through LangGraph,
    tools and the real OpenAI Realtime audio renderer. Live PSTN speech-to-text
    forwarding is intentionally not claimed by this lab mode.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.metrics = BridgeMetrics()
        self.stream_sid = ""
        self.call_sid = ""
        self.session_id = None
        self.output_active = False
        self.output_cancelled = asyncio.Event()
        self.send_lock = asyncio.Lock()
        self.output_task: asyncio.Task | None = None

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
                raise RuntimeError("Voice channel account not found")
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
                raise RuntimeError("Voice runtime user is unavailable")
            # Objects are expire_on_commit=False and only scalar fields are needed.
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
            }
            session.session_metadata = metadata
            db.add(VoiceEvent(
                tenant_id=session.tenant_id,
                voice_session_id=session.id,
                direction="system",
                event_type="twilio_media_stream",
                status="completed",
                audio_bytes=self.metrics.inbound_bytes + self.metrics.outbound_bytes,
                event_metadata=metadata["twilio_bridge"],
            ))
            await db.commit()

    async def _produce_business_audio(
        self,
        *,
        account: ChannelAccount,
        runtime_user: User,
        from_address: str,
        transcript: str,
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
                )
            self.session_id = result.session.id
            if result.deduplicated or not result.audio_data:
                return

            frames = list(iter_mulaw_frames(result.audio_data))
            if not frames:
                return
            self.output_active = True
            sleep_seconds = max(0.0, TWILIO_MEDIA_FRAME_MS / 1000 / settings.voice_bridge_playback_speed)
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
            logger.exception("Twilio bridge business turn failed")
            raise
        finally:
            self.output_active = False

    async def run(self) -> None:
        await self.websocket.accept()
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
                    params = start["custom_parameters"]
                    provider_account_id = str(params.get("provider_account_id") or "")
                    lab_token = str(params.get("lab_token") or "")
                    from_address = str(params.get("from_address") or "")
                    transcript = str(params.get("lab_transcript") or "")
                    if not provider_account_id or not from_address:
                        raise RuntimeError("Twilio start customParameters require provider_account_id and from_address")
                    if not settings.voice_bridge_lab_enabled:
                        raise RuntimeError("v0.10 bridge lab mode is disabled")
                    if lab_token != settings.voice_bridge_lab_token:
                        raise RuntimeError("invalid voice bridge lab token")
                    if not transcript:
                        raise RuntimeError("v0.10 lab mode requires lab_transcript")
                    account, runtime_user = await self._load_account_and_user(provider_account_id)
                    self.output_task = asyncio.create_task(self._produce_business_audio(
                        account=account,
                        runtime_user=runtime_user,
                        from_address=from_address,
                        transcript=transcript,
                    ))
                    continue

                if event == "media":
                    self.metrics.inbound_frames += 1
                    self.metrics.inbound_bytes += int(parsed["audio_bytes"])
                    if self.output_active and settings.voice_barge_in_enabled and not self.output_cancelled.is_set():
                        self.output_cancelled.set()
                        self.metrics.barge_in_count += 1
                        await self._send_json(build_clear_message(stream_sid=self.stream_sid))
                        self.metrics.clears_sent += 1
                    continue

                if event == "mark":
                    self.metrics.marks_received += 1
                    continue

                if event == "dtmf":
                    # v0.10 only audits DTMF at protocol level; business routing is later.
                    continue

                if event == "stop":
                    break
        except Exception as exc:
            logger.warning("Twilio media bridge closed with error: %s", exc)
            try:
                await self.websocket.close(code=1008, reason=str(exc)[:120])
            except Exception:
                pass
        finally:
            if self.output_task is not None:
                try:
                    await asyncio.wait_for(self.output_task, timeout=settings.openai_realtime_timeout_seconds + 15)
                except asyncio.TimeoutError:
                    self.output_task.cancel()
                except Exception:
                    pass
            try:
                await self._persist_bridge_summary(interrupted=self.output_cancelled.is_set())
            except Exception:
                pass
            try:
                await self.websocket.close()
            except Exception:
                pass
