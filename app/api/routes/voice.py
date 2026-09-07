from __future__ import annotations

from typing import Annotated
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, WebSocket
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.channel import ChannelAccount, ChannelEvent
from app.models.user import User, UserRole
from app.models.voice import VoiceEvent, VoiceSession
from app.schemas.channel import ChannelAccountRead, ChannelEventRead
from app.schemas.voice import (
    MockVoiceTurnRequest,
    MockVoiceTurnResponse,
    RealtimeProbeRequest,
    RealtimeProbeResponse,
    VoiceAccountUpsert,
    VoiceEventRead,
    VoiceSessionRead,
)
from app.services.voice_service import VoiceService
from app.services.twilio_voice_service import TwilioVoiceService
from app.voice.realtime_client import OpenAIRealtimeClient, RealtimeVoiceError
from app.voice.twilio_bridge import TwilioMediaBridge
from app.voice.twilio_protocol import (
    TWILIO_MEDIA_CHANNELS,
    TWILIO_MEDIA_ENCODING,
    TWILIO_MEDIA_SAMPLE_RATE,
    TwilioProtocolError,
    build_bidirectional_twiml,
)
from app.voice.twilio_security import TwilioSecurityError, validate_http_signature


router = APIRouter(prefix="/channels/voice", tags=["voice"])
TenantAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
ACCOUNT_PATTERN = r"^[A-Za-z0-9_.-]{1,200}$"


@router.get("/config")
async def voice_config() -> dict:
    production_urls_ready = bool(
        settings.twilio_public_base_url
        and str(settings.twilio_public_base_url).startswith("https://")
        and settings.twilio_wss_base_url
        and str(settings.twilio_wss_base_url).startswith("wss://")
    )
    return {
        "openai_realtime": {
            "model": settings.openai_realtime_model,
            "voice": settings.openai_realtime_voice,
            "server_transport": "websocket",
            "lab_audio_format": "audio/pcmu",
            "max_session_minutes": settings.voice_session_max_minutes,
            "function_calling_capable": True,
        },
        "speech_to_text": {
            "model": settings.openai_transcribe_model,
            "input_format": "Twilio audio/x-mulaw 8000 Hz",
            "turn_detection": "local-rms-vad",
            "first_turn_only": settings.voice_production_first_turn_only,
        },
        "twilio_media_streams": {
            "transport": "websocket",
            "bidirectional": "Connect/Stream",
            "encoding": TWILIO_MEDIA_ENCODING,
            "sample_rate_hz": TWILIO_MEDIA_SAMPLE_RATE,
            "channels": TWILIO_MEDIA_CHANNELS,
            "live_audio_bridge": "v0.11_production_hardening",
            "barge_in": settings.voice_barge_in_enabled,
            "lab_mode": settings.voice_bridge_lab_enabled,
            "production_mode_enabled": settings.voice_production_enabled,
            "signature_required": settings.twilio_require_signature,
            "production_urls_ready": production_urls_ready,
            "lab_transcript_injection": True,
            "production_transcript_injection": False,
            "production_pstn_connected": False,
        },
        "native_openai_sip": {"supported_by_provider": True, "wired_in_platform": False},
        "secrets_in_database": False,
    }


@router.put("/tenant/accounts/{provider_account_id}", response_model=ChannelAccountRead)
async def upsert_voice_account(
    payload: VoiceAccountUpsert,
    current_user: TenantAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    if payload.outbound_mode == "twilio_media_stream" and not payload.access_token_env:
        raise HTTPException(status_code=422, detail="twilio_media_stream mode requires access_token_env")
    account = (
        await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.provider == "twilio",
                ChannelAccount.provider_account_id == provider_account_id,
            )
        )
    ).scalar_one_or_none()
    if account is not None and account.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=409, detail="voice provider_account_id is already assigned to another tenant")
    if account is None:
        account = ChannelAccount(
            tenant_id=current_user.tenant_id,
            runtime_user_id=current_user.id,
            channel="voice",
            provider="twilio",
            provider_account_id=provider_account_id,
        )
        db.add(account)
    account.runtime_user_id = current_user.id
    account.business_account_id = payload.account_sid
    account.display_phone_number = payload.display_phone_number
    account.outbound_mode = payload.outbound_mode
    account.access_token_env = payload.access_token_env
    account.is_active = payload.is_active
    await db.commit(); await db.refresh(account)
    return account


@router.get("/tenant/accounts/{provider_account_id}/production-readiness")
async def production_readiness(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    account = (
        await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.tenant_id == current_user.tenant_id,
                ChannelAccount.channel == "voice",
                ChannelAccount.provider == "twilio",
                ChannelAccount.provider_account_id == provider_account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Voice channel account not found")
    token_env = str(account.access_token_env or "")
    checks = {
        "production_enabled": settings.voice_production_enabled,
        "signature_required": settings.twilio_require_signature,
        "https_public_base_url": bool(settings.twilio_public_base_url and str(settings.twilio_public_base_url).startswith("https://")),
        "wss_public_base_url": bool(settings.twilio_wss_base_url and str(settings.twilio_wss_base_url).startswith("wss://")),
        "account_mode_twilio_media_stream": account.outbound_mode == "twilio_media_stream",
        "account_sid_configured": bool(account.business_account_id),
        "display_phone_configured": bool(account.display_phone_number),
        "auth_token_env_configured": bool(token_env),
        "auth_token_secret_available": bool(token_env and os.environ.get(token_env)),
    }
    return {
        "provider_account_id": provider_account_id,
        "tenant_id": str(account.tenant_id),
        "ready_for_twilio_configuration": all(checks.values()),
        "checks": checks,
        "incoming_webhook_path": f"{settings.api_v1_prefix}/channels/voice/twilio/incoming/{provider_account_id}",
        "call_status_callback_path": f"{settings.api_v1_prefix}/channels/voice/twilio/call-status/{provider_account_id}",
        "media_stream_path": f"{settings.api_v1_prefix}/channels/voice/twilio/media/{provider_account_id}",
        "stream_status_callback_path": f"{settings.api_v1_prefix}/channels/voice/twilio/stream-status/{provider_account_id}",
        "pstn_connected": False,
    }


async def _production_account(db: AsyncSession, provider_account_id: str) -> ChannelAccount:
    if not settings.voice_production_enabled:
        raise HTTPException(status_code=503, detail="VOICE_PRODUCTION_ENABLED is disabled")
    account = await TwilioVoiceService().get_account(db=db, provider_account_id=provider_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Voice/Twilio account not found")
    if account.outbound_mode != "twilio_media_stream":
        raise HTTPException(status_code=409, detail="Voice account is not configured for twilio_media_stream")
    return account


def _form_dict(form) -> dict[str, str]:
    return {str(key): str(value) for key, value in form.multi_items()}


@router.post("/twilio/incoming/{provider_account_id}", response_class=PlainTextResponse)
async def twilio_incoming_call(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    account = await _production_account(db, provider_account_id)
    form = _form_dict(await request.form())
    try:
        if not validate_http_signature(request=request, account=account, form=form):
            raise HTTPException(status_code=403, detail="Invalid X-Twilio-Signature")
        TwilioVoiceService.ensure_account_sid(account, form.get("AccountSid", ""))
    except TwilioSecurityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    call_sid = str(form.get("CallSid") or "")
    from_address = str(form.get("From") or form.get("Caller") or "")
    to_address = str(form.get("To") or form.get("Called") or account.display_phone_number or "")
    if not call_sid or not from_address:
        raise HTTPException(status_code=422, detail="Twilio incoming webhook requires CallSid and From")
    if account.display_phone_number and to_address and account.display_phone_number != to_address:
        raise HTTPException(status_code=403, detail="Called number does not match configured tenant Voice number")

    await TwilioVoiceService().record_channel_event(
        db=db,
        account=account,
        provider_event_id=f"incoming:{call_sid}",
        event_type="incoming_call",
        status=str(form.get("CallStatus") or "received"),
        direction="inbound",
        form=form,
    )
    if not settings.twilio_wss_base_url or not settings.twilio_public_base_url:
        raise HTTPException(status_code=503, detail="Twilio public URLs are not configured")
    stream_url = (
        str(settings.twilio_wss_base_url).rstrip("/")
        + settings.api_v1_prefix
        + f"/channels/voice/twilio/media/{provider_account_id}"
    )
    stream_status_url = (
        str(settings.twilio_public_base_url).rstrip("/")
        + settings.api_v1_prefix
        + f"/channels/voice/twilio/stream-status/{provider_account_id}"
    )
    xml = build_bidirectional_twiml(
        stream_url=stream_url,
        status_callback_url=stream_status_url,
        stream_name="ai-sales-agent",
        custom_parameters={
            "provider_account_id": provider_account_id,
            "from_address": from_address,
            "to_address": to_address,
            "call_sid": call_sid,
        },
    )
    return PlainTextResponse(xml, media_type="application/xml")


@router.post("/twilio/call-status/{provider_account_id}")
async def twilio_call_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    account = await _production_account(db, provider_account_id)
    form = _form_dict(await request.form())
    try:
        if not validate_http_signature(request=request, account=account, form=form):
            raise HTTPException(status_code=403, detail="Invalid X-Twilio-Signature")
        TwilioVoiceService.ensure_account_sid(account, form.get("AccountSid", ""))
    except TwilioSecurityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    call_sid = str(form.get("CallSid") or "")
    call_status = str(form.get("CallStatus") or "unknown")
    if not call_sid:
        raise HTTPException(status_code=422, detail="CallSid is required")
    event, duplicate = await TwilioVoiceService().record_channel_event(
        db=db,
        account=account,
        provider_event_id=f"call:{call_sid}:{call_status}",
        event_type="call_status",
        status=call_status,
        direction="system",
        form=form,
    )
    await TwilioVoiceService().annotate_voice_session(
        db=db,
        account=account,
        call_sid=call_sid,
        namespace="twilio_call_status",
        payload=form,
    )
    return {"status": "accepted", "duplicate": duplicate, "event_id": str(event.id)}


@router.post("/twilio/stream-status/{provider_account_id}")
async def twilio_stream_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    account = await _production_account(db, provider_account_id)
    form = _form_dict(await request.form())
    try:
        if not validate_http_signature(request=request, account=account, form=form):
            raise HTTPException(status_code=403, detail="Invalid X-Twilio-Signature")
        TwilioVoiceService.ensure_account_sid(account, form.get("AccountSid", ""))
    except TwilioSecurityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    call_sid = str(form.get("CallSid") or "")
    stream_sid = str(form.get("StreamSid") or "")
    stream_event = str(form.get("StreamEvent") or "unknown")
    if not call_sid or not stream_sid:
        raise HTTPException(status_code=422, detail="CallSid and StreamSid are required")
    event, duplicate = await TwilioVoiceService().record_channel_event(
        db=db,
        account=account,
        provider_event_id=f"stream:{stream_sid}:{stream_event}",
        event_type="stream_status",
        status=stream_event,
        direction="system",
        form=form,
    )
    await TwilioVoiceService().annotate_voice_session(
        db=db,
        account=account,
        call_sid=call_sid,
        namespace="twilio_stream_status",
        payload=form,
    )
    return {"status": "accepted", "duplicate": duplicate, "event_id": str(event.id)}


@router.get("/channel-events", response_model=list[ChannelEventRead])
async def list_voice_channel_events(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=200),
):
    return list((await db.execute(
        select(ChannelEvent).where(
            ChannelEvent.tenant_id == current_user.tenant_id,
            ChannelEvent.channel == "voice",
            ChannelEvent.provider == "twilio",
        ).order_by(ChannelEvent.created_at.desc()).limit(limit)
    )).scalars().all())


@router.websocket("/twilio/media")
async def twilio_media_stream_lab(websocket: WebSocket):
    """Endpoint de laboratorio preservado para regressao da v0.10."""
    await TwilioMediaBridge(websocket, mode="lab").run()


@router.websocket("/twilio/media/{provider_account_id}")
async def twilio_media_stream_production(
    websocket: WebSocket,
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    """Endpoint de producao: assinatura Twilio + audio real, sem lab_transcript."""
    await TwilioMediaBridge(
        websocket,
        mode="production",
        provider_account_id=provider_account_id,
    ).run()


@router.post("/realtime/probe", response_model=RealtimeProbeResponse)
async def realtime_probe(payload: RealtimeProbeRequest, current_user: CurrentUser):
    try:
        result = await OpenAIRealtimeClient().text_probe(
            message=payload.message,
            safety_identifier=f"tenant:{current_user.tenant_id}:user:{current_user.id}",
        )
    except RealtimeVoiceError as exc:
        raise HTTPException(status_code=502, detail={"code": "realtime_error", "message": str(exc)}) from exc
    return RealtimeProbeResponse(
        model=settings.openai_realtime_model,
        session_id=result.session_id,
        response_id=result.response_id,
        text=result.text,
        event_count=result.event_count,
        latency_ms=result.latency_ms,
        usage=result.usage,
    )


@router.get("/twiml-preview", response_class=PlainTextResponse)
async def twiml_preview(current_user: CurrentUser, stream_url: str = Query(..., min_length=8, max_length=1000)):
    try:
        xml = build_bidirectional_twiml(stream_url=stream_url)
    except TwilioProtocolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PlainTextResponse(xml, media_type="application/xml")


@router.post("/mock/accounts/{provider_account_id}/turns", response_model=MockVoiceTurnResponse)
async def mock_voice_turn(
    payload: MockVoiceTurnRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_account_id: Annotated[str, Path(pattern=ACCOUNT_PATTERN)],
):
    account = (
        await db.execute(
            select(ChannelAccount).where(
                ChannelAccount.tenant_id == current_user.tenant_id,
                ChannelAccount.channel == "voice",
                ChannelAccount.provider == "twilio",
                ChannelAccount.provider_account_id == provider_account_id,
                ChannelAccount.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Voice channel account not found")
    try:
        session, dedup, audio_transcript = await VoiceService().mock_turn(
            db=db,
            current_user=current_user,
            account=account,
            provider_call_id=payload.provider_call_id,
            from_address=payload.from_address,
            transcript=payload.transcript,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": type(exc).__name__, "message": str(exc)}) from exc
    return MockVoiceTurnResponse(deduplicated=dedup, session=session, realtime_audio_transcript=audio_transcript)


@router.get("/sessions", response_model=list[VoiceSessionRead])
async def list_voice_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
):
    return list((await db.execute(
        select(VoiceSession).where(VoiceSession.tenant_id == current_user.tenant_id)
        .order_by(VoiceSession.created_at.desc()).limit(limit)
    )).scalars().all())


@router.get("/sessions/{session_id}/events", response_model=list[VoiceEventRead])
async def list_voice_events(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: uuid.UUID,
):
    session = (await db.execute(select(VoiceSession).where(
        VoiceSession.id == session_id, VoiceSession.tenant_id == current_user.tenant_id
    ))).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    return list((await db.execute(
        select(VoiceEvent).where(VoiceEvent.voice_session_id == session.id)
        .order_by(VoiceEvent.created_at)
    )).scalars().all())
