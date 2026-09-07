from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import get_sales_graph, internal_thread_id
from app.agent.state import SalesAgentContext
from app.core.config import settings
from app.llm.factory import create_llm_provider
from app.models.channel import ChannelAccount
from app.models.conversation import Channel, Conversation
from app.models.customer import Customer
from app.models.message import Message, MessageRole
from app.models.user import User
from app.models.voice import VoiceEvent, VoiceSession
from app.observability.context import bind_context
from app.observability.metrics import VOICE_SESSIONS, VOICE_SESSION_DURATION, enabled as metrics_enabled
from app.observability.tracing import tracer
from app.services.llm_service import LLMService
from app.services.tenant_config_service import TenantConfigService
from app.services.tool_service import ToolService
from app.tools.registry import get_tool_registry
from app.voice.realtime_client import OpenAIRealtimeClient


@dataclass(slots=True)
class VoiceTurnResult:
    session: VoiceSession
    deduplicated: bool
    audio_transcript: str
    audio_data: bytes


class VoiceService:
    @staticmethod
    def _thread_id(from_address: str) -> str:
        compact = re.sub(r"[^A-Za-z0-9_.-]", "", from_address)
        if not compact:
            compact = uuid.uuid4().hex[:12]
        return ("voice-" + compact)[:100]

    async def mock_turn(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        account: ChannelAccount,
        provider_call_id: str,
        from_address: str,
        transcript: str,
    ) -> tuple[VoiceSession, bool, str]:
        result = await self._process_turn(
            db=db,
            current_user=current_user,
            account=account,
            provider="mock_twilio",
            transport="mock_realtime_websocket",
            event_source="mock_voice_turn",
            provider_call_id=provider_call_id,
            from_address=from_address,
            transcript=transcript,
        )
        return result.session, result.deduplicated, result.audio_transcript

    async def bridge_turn(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        account: ChannelAccount,
        provider_call_id: str,
        from_address: str,
        transcript: str,
        event_source: str = "twilio_media_stream_lab",
    ) -> VoiceTurnResult:
        return await self._process_turn(
            db=db,
            current_user=current_user,
            account=account,
            provider="twilio",
            transport="twilio_media_stream",
            event_source=event_source,
            provider_call_id=provider_call_id,
            from_address=from_address,
            transcript=transcript,
        )

    async def _process_turn(
        self,
        *,
        db: AsyncSession,
        current_user: User,
        account: ChannelAccount,
        provider: str,
        transport: str,
        event_source: str,
        provider_call_id: str,
        from_address: str,
        transcript: str,
    ) -> VoiceTurnResult:
        existing = (
            await db.execute(
                select(VoiceSession).where(
                    VoiceSession.tenant_id == current_user.tenant_id,
                    VoiceSession.provider == provider,
                    VoiceSession.provider_call_id == provider_call_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            audio_transcript = str((existing.session_metadata or {}).get("realtime_audio_transcript") or "")
            return VoiceTurnResult(existing, True, audio_transcript, b"")

        runtime_user = (
            await db.execute(
                select(User).where(
                    User.id == account.runtime_user_id,
                    User.tenant_id == current_user.tenant_id,
                    User.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if runtime_user is None:
            raise RuntimeError("voice runtime user is unavailable")

        thread_id = self._thread_id(from_address)
        session = VoiceSession(
            tenant_id=current_user.tenant_id,
            channel_account_id=account.id,
            runtime_user_id=runtime_user.id,
            provider=provider,
            provider_call_id=provider_call_id,
            transport=transport,
            external_thread_id=thread_id,
            from_address=from_address,
            to_address=account.display_phone_number or account.provider_account_id,
            status="processing",
            realtime_model=settings.openai_realtime_model,
            voice=settings.openai_realtime_voice,
            input_transcript=transcript,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        bind_context(tenant_id=str(current_user.tenant_id), call_sid=provider_call_id)
        started = time.perf_counter()

        try:
            external_id = f"voice:{from_address}"
            customer = (
                await db.execute(
                    select(Customer).where(
                        Customer.tenant_id == current_user.tenant_id,
                        Customer.external_id == external_id,
                    )
                )
            ).scalar_one_or_none()
            if customer is None:
                customer = Customer(
                    tenant_id=current_user.tenant_id,
                    external_id=external_id,
                    name="Voice Customer",
                    phone=from_address,
                )
                db.add(customer)
                await db.flush()

            conversation = (
                await db.execute(
                    select(Conversation).where(
                        Conversation.tenant_id == current_user.tenant_id,
                        Conversation.customer_id == customer.id,
                        Conversation.channel == Channel.VOICE,
                        Conversation.status == "open",
                    ).order_by(Conversation.created_at.desc())
                )
            ).scalars().first()
            if conversation is None:
                conversation = Conversation(
                    tenant_id=current_user.tenant_id,
                    customer_id=customer.id,
                    channel=Channel.VOICE,
                    status="open",
                )
                db.add(conversation)
                await db.flush()
            session.conversation_id = conversation.id
            bind_context(conversation_id=str(conversation.id))

            db.add(Message(
                tenant_id=current_user.tenant_id,
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=transcript,
            ))
            db.add(VoiceEvent(
                tenant_id=current_user.tenant_id,
                voice_session_id=session.id,
                direction="inbound",
                event_type="transcript",
                transcript=transcript,
                event_metadata={"source": event_source},
            ))
            await db.commit()

            tenant_config = await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)
            registry = get_tool_registry().filtered(tenant_config.enabled_tools)
            context = SalesAgentContext(
                db=db,
                current_user=runtime_user,
                llm_service=LLMService(create_llm_provider()),
                tool_service=ToolService(registry, tenant_config=tenant_config),
                tenant_config=tenant_config,
                client_idempotency_key=f"voice:{provider}:{provider_call_id}",
            )
            graph = get_sales_graph()
            config = {
                "configurable": {
                    "thread_id": internal_thread_id(
                        tenant_id=str(current_user.tenant_id),
                        external_thread_id=thread_id,
                    )
                }
            }
            before = await graph.aget_state(config)
            if tuple(getattr(before, "interrupts", ()) or ()):
                answer = "Esta chamada aguarda atendimento humano antes de continuar."
            else:
                with tracer("app.agent").start_as_current_span("agent.langgraph.voice") as span:
                    span.set_attribute("saas.tenant.id", str(current_user.tenant_id))
                    span.set_attribute("agent.thread_id", thread_id)
                    await graph.ainvoke({
                        "latest_input": transcript,
                        "external_thread_id": thread_id,
                        "tenant_id": str(current_user.tenant_id),
                        "messages": [{"role": "user", "content": transcript}],
                        "human_required": False,
                        "human_review_status": "none",
                        "human_review_note": "",
                        "reviewed_by_user_id": "",
                        "final_output": "",
                    }, config=config, context=context)
                after = await graph.aget_state(config)
                values = dict(getattr(after, "values", {}) or {})
                pending = tuple(getattr(after, "interrupts", ()) or ())
                answer = str(values.get("final_output") or "")
                if pending and not answer:
                    answer = "Recebi seu pedido. Vou encaminhar esta chamada para atendimento humano."
                if not answer:
                    answer = "Recebi sua mensagem."

            audio = await OpenAIRealtimeClient().render_text_audio(
                text=answer,
                safety_identifier=f"tenant:{current_user.tenant_id}:voice:{from_address}",
            )
            db.add(Message(
                tenant_id=current_user.tenant_id,
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=answer,
            ))
            db.add(VoiceEvent(
                tenant_id=current_user.tenant_id,
                voice_session_id=session.id,
                direction="outbound",
                event_type="realtime_audio",
                transcript=audio.transcript,
                audio_bytes=audio.audio_bytes,
                event_metadata={
                    "model": settings.openai_realtime_model,
                    "voice": settings.openai_realtime_voice,
                    "format": "audio/pcmu",
                    "audio_sha256": audio.audio_sha256,
                    "realtime_response_id": audio.response_id,
                },
            ))
            session.assistant_text = answer
            session.audio_bytes = audio.audio_bytes
            session.audio_sha256 = audio.audio_sha256
            session.realtime_session_id = audio.session_id
            session.realtime_response_id = audio.response_id
            session.latency_ms = int((time.perf_counter() - started) * 1000)
            session.status = "completed"
            session.session_metadata = {
                "realtime_audio_transcript": audio.transcript,
                "realtime_event_count": audio.event_count,
                "realtime_latency_ms": audio.latency_ms,
                "realtime_usage": audio.usage,
            }
            await db.commit()
            await db.refresh(session)
            if metrics_enabled():
                VOICE_SESSIONS.labels(provider, "completed").inc()
                VOICE_SESSION_DURATION.labels(provider).observe(max(0.0, session.latency_ms / 1000))
            return VoiceTurnResult(session, False, audio.transcript, audio.audio_data)
        except Exception as exc:
            await db.rollback()
            failed = (
                await db.execute(select(VoiceSession).where(VoiceSession.id == session.id))
            ).scalar_one_or_none()
            if failed is not None:
                failed.status = "failed"
                failed.error_code = type(exc).__name__[:100]
                failed.error_message = str(exc)[:2000]
                failed.latency_ms = int((time.perf_counter() - started) * 1000)
                await db.commit()
                if metrics_enabled():
                    VOICE_SESSIONS.labels(provider, "failed").inc()
                    VOICE_SESSION_DURATION.labels(provider).observe(max(0.0, failed.latency_ms / 1000))
            raise
