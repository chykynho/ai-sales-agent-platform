from __future__ import annotations

import os
import uuid

import httpx
from sqlalchemy import select

from app.agent.runtime import get_sales_graph, internal_thread_id
from app.channels.whatsapp_protocol import extract_text_messages, payload_hash, verify_signature
from app.agent.state import SalesAgentContext
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.llm.factory import create_llm_provider
from app.models.channel import ChannelAccount, ChannelEvent
from app.models.conversation import Channel, Conversation
from app.models.customer import Customer
from app.models.message import Message, MessageRole
from app.models.user import User
from app.services.llm_service import LLMService
from app.services.tenant_config_service import TenantConfigService
from app.services.tool_service import ToolService
from app.tools.registry import get_tool_registry


class WhatsAppService:
    verify_signature = staticmethod(verify_signature)
    payload_hash = staticmethod(payload_hash)
    extract_text_messages = staticmethod(extract_text_messages)

    @staticmethod
    async def send_text(*, account: ChannelAccount, to: str, text: str) -> str:
        if account.outbound_mode == "mock":
            return f"mock-wa-{uuid.uuid4()}"

        if account.outbound_mode != "meta_cloud":
            raise RuntimeError(f"unsupported outbound_mode: {account.outbound_mode}")
        if not account.access_token_env:
            raise RuntimeError("real WhatsApp mode requires access_token_env")
        token = os.getenv(account.access_token_env)
        if not token:
            raise RuntimeError(f"environment variable {account.access_token_env} is not configured")

        url = (
            f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
            f"{account.provider_account_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=settings.whatsapp_http_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.is_error:
            raise RuntimeError(f"Meta send failed HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        messages = data.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise RuntimeError("Meta send response did not contain messages[0].id")
        return str(messages[0]["id"])


async def process_whatsapp_event(event_id: str) -> None:
    """Background processor. It opens its own DB session after webhook ACK."""
    event_uuid = uuid.UUID(event_id)
    async with AsyncSessionLocal() as db:
        event = (await db.execute(select(ChannelEvent).where(ChannelEvent.id == event_uuid))).scalar_one_or_none()
        if event is None or event.status not in {"accepted", "retry"}:
            return
        account = (
            await db.execute(select(ChannelAccount).where(ChannelAccount.id == event.channel_account_id))
        ).scalar_one_or_none()
        if account is None or not account.is_active:
            event.status = "failed"
            event.error_code = "channel_account_inactive"
            await db.commit()
            return
        runtime_user = (
            await db.execute(
                select(User).where(User.id == account.runtime_user_id, User.tenant_id == account.tenant_id)
            )
        ).scalar_one_or_none()
        if runtime_user is None or not runtime_user.is_active:
            event.status = "failed"
            event.error_code = "runtime_user_unavailable"
            await db.commit()
            return

        event.status = "processing"
        await db.commit()
        try:
            external_id = f"whatsapp:{event.from_address}"
            customer = (
                await db.execute(
                    select(Customer).where(
                        Customer.tenant_id == event.tenant_id,
                        Customer.external_id == external_id,
                    )
                )
            ).scalar_one_or_none()
            if customer is None:
                profile_name = str((event.event_metadata or {}).get("profile_name") or "WhatsApp Customer")
                customer = Customer(
                    tenant_id=event.tenant_id,
                    external_id=external_id,
                    name=profile_name[:200] or "WhatsApp Customer",
                    phone=event.from_address,
                )
                db.add(customer)
                await db.flush()

            conversation = (
                await db.execute(
                    select(Conversation).where(
                        Conversation.tenant_id == event.tenant_id,
                        Conversation.customer_id == customer.id,
                        Conversation.channel == Channel.WHATSAPP,
                        Conversation.status == "open",
                    ).order_by(Conversation.created_at.desc())
                )
            ).scalars().first()
            if conversation is None:
                conversation = Conversation(
                    tenant_id=event.tenant_id,
                    customer_id=customer.id,
                    channel=Channel.WHATSAPP,
                    status="open",
                )
                db.add(conversation)
                await db.flush()

            event.conversation_id = conversation.id
            db.add(
                Message(
                    tenant_id=event.tenant_id,
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content=event.content_text or "",
                )
            )
            await db.commit()

            tenant_config = await TenantConfigService().get(db=db, tenant_id=event.tenant_id)
            registry = get_tool_registry().filtered(tenant_config.enabled_tools)
            context = SalesAgentContext(
                db=db,
                current_user=runtime_user,
                llm_service=LLMService(create_llm_provider()),
                tool_service=ToolService(registry, tenant_config=tenant_config),
                tenant_config=tenant_config,
                client_idempotency_key=f"whatsapp:{event.provider_event_id}",
            )
            external_thread_id = f"wa-{event.from_address}"[:100]
            config = {
                "configurable": {
                    "thread_id": internal_thread_id(
                        tenant_id=str(event.tenant_id),
                        external_thread_id=external_thread_id,
                    )
                }
            }
            graph = get_sales_graph()
            state_before = await graph.aget_state(config)
            pending_before = tuple(getattr(state_before, "interrupts", ()) or ())
            if pending_before:
                output = "Esta conversa aguarda atendimento humano antes de continuar."
            else:
                await graph.ainvoke(
                    {
                        "latest_input": event.content_text or "",
                        "external_thread_id": external_thread_id,
                        "tenant_id": str(event.tenant_id),
                        "messages": [{"role": "user", "content": event.content_text or ""}],
                        "human_required": False,
                        "human_review_status": "none",
                        "human_review_note": "",
                        "reviewed_by_user_id": "",
                        "final_output": "",
                    },
                    config=config,
                    context=context,
                )
                state_after = await graph.aget_state(config)
                values = dict(getattr(state_after, "values", {}) or {})
                pending_after = tuple(getattr(state_after, "interrupts", ()) or ())
                output = str(values.get("final_output") or "")
                if pending_after and not output:
                    output = "Recebi seu pedido. Vou encaminhar esta conversa para atendimento humano."
                if not output:
                    output = "Recebi sua mensagem."

            provider_out_id = await WhatsAppService.send_text(
                account=account,
                to=event.from_address or "",
                text=output,
            )
            db.add(
                Message(
                    tenant_id=event.tenant_id,
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=output,
                )
            )
            db.add(
                ChannelEvent(
                    tenant_id=event.tenant_id,
                    channel_account_id=account.id,
                    conversation_id=conversation.id,
                    provider=account.provider,
                    channel="whatsapp",
                    provider_event_id=provider_out_id,
                    direction="outbound",
                    event_type="text",
                    status="sent",
                    from_address=account.display_phone_number or account.provider_account_id,
                    to_address=event.from_address,
                    content_text=output,
                    event_metadata={"outbound_mode": account.outbound_mode},
                )
            )
            event.status = "completed"
            await db.commit()
        except Exception as exc:
            await db.rollback()
            event = (await db.execute(select(ChannelEvent).where(ChannelEvent.id == event_uuid))).scalar_one_or_none()
            if event is not None:
                event.status = "failed"
                event.error_code = type(exc).__name__[:100]
                event.error_message = str(exc)[:2000]
                await db.commit()
