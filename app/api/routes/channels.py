from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Path, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.channel import ChannelAccount, ChannelEvent
from app.models.user import User, UserRole
from app.schemas.channel import (
    ChannelAccountRead,
    ChannelEventRead,
    WhatsAppAccountUpsert,
    WhatsAppWebhookAcceptResponse,
)
from app.services.whatsapp_service import WhatsAppService, process_whatsapp_event

router = APIRouter(prefix="/channels", tags=["channels"])
TenantAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
PHONE_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,200}$"


@router.get("/config")
async def channel_config() -> dict:
    return {
        "whatsapp": {
            "provider": "meta_cloud",
            "graph_api_version": settings.whatsapp_graph_api_version,
            "webhook_signature": "X-Hub-Signature-256/HMAC-SHA256",
            "webhook_processing": "ack-first-background",
            "tenant_resolution": "phone_number_id",
            "outbound_modes": ["mock", "meta_cloud"],
            "secrets_in_database": False,
        }
    }


@router.get("/tenant/accounts", response_model=list[ChannelAccountRead])
async def list_accounts(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    return list(
        (
            await db.execute(
                select(ChannelAccount)
                .where(ChannelAccount.tenant_id == current_user.tenant_id)
                .order_by(ChannelAccount.created_at)
            )
        ).scalars().all()
    )


@router.put("/tenant/whatsapp/{phone_number_id}", response_model=ChannelAccountRead)
async def upsert_whatsapp_account(
    payload: WhatsAppAccountUpsert,
    current_user: TenantAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    phone_number_id: Annotated[str, Path(pattern=PHONE_ID_PATTERN)],
):
    if payload.outbound_mode == "meta_cloud" and not payload.access_token_env:
        raise HTTPException(status_code=422, detail="meta_cloud mode requires access_token_env")
    account = (
        await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.provider == "meta_cloud",
                ChannelAccount.provider_account_id == phone_number_id,
            )
        )
    ).scalar_one_or_none()
    if account is not None and account.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=409, detail="phone_number_id is already assigned to another tenant")
    if account is None:
        account = ChannelAccount(
            tenant_id=current_user.tenant_id,
            runtime_user_id=current_user.id,
            channel="whatsapp",
            provider="meta_cloud",
            provider_account_id=phone_number_id,
        )
        db.add(account)
    account.runtime_user_id = current_user.id
    account.business_account_id = payload.business_account_id
    account.display_phone_number = payload.display_phone_number
    account.outbound_mode = payload.outbound_mode
    account.access_token_env = payload.access_token_env
    account.is_active = payload.is_active
    await db.commit()
    await db.refresh(account)
    return account


@router.get("/whatsapp/events", response_model=list[ChannelEventRead])
async def list_whatsapp_events(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list(
        (
            await db.execute(
                select(ChannelEvent)
                .where(ChannelEvent.tenant_id == current_user.tenant_id, ChannelEvent.channel == "whatsapp")
                .order_by(ChannelEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token and hub_challenge:
        return PlainTextResponse(hub_challenge, status_code=200)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed")


@router.post("/whatsapp/webhook", response_model=WhatsAppWebhookAcceptResponse)
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
):
    raw_body = await request.body()
    if len(raw_body) > settings.whatsapp_webhook_max_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    if not WhatsAppService.verify_signature(raw_body=raw_body, signature_header=signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    try:
        payload = __import__("json").loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc

    if payload.get("object") != "whatsapp_business_account":
        return WhatsAppWebhookAcceptResponse(accepted=0, duplicate=0, ignored=1)

    accepted = duplicate = ignored = 0
    raw_hash = WhatsAppService.payload_hash(raw_body)
    for item in WhatsAppService.extract_text_messages(payload):
        account = (
            await db.execute(
                select(ChannelAccount).where(
                    ChannelAccount.provider == "meta_cloud",
                    ChannelAccount.provider_account_id == item["phone_number_id"],
                    ChannelAccount.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if account is None:
            ignored += 1
            continue
        existing = (
            await db.execute(
                select(ChannelEvent.id).where(
                    ChannelEvent.provider == "meta_cloud",
                    ChannelEvent.provider_event_id == item["provider_event_id"],
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            duplicate += 1
            continue
        event = ChannelEvent(
            tenant_id=account.tenant_id,
            channel_account_id=account.id,
            provider="meta_cloud",
            channel="whatsapp",
            provider_event_id=item["provider_event_id"],
            direction="inbound",
            event_type="text",
            status="accepted",
            from_address=item["from"],
            to_address=item["display_phone_number"] or item["phone_number_id"],
            content_text=item["text"],
            raw_payload_hash=raw_hash,
            event_metadata={"profile_name": item["profile_name"], "phone_number_id": item["phone_number_id"]},
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        background_tasks.add_task(process_whatsapp_event, str(event.id))
        accepted += 1

    return WhatsAppWebhookAcceptResponse(accepted=accepted, duplicate=duplicate, ignored=ignored)
