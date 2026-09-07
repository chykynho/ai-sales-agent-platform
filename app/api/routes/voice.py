from __future__ import annotations

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, WebSocket
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models.channel import ChannelAccount
from app.models.user import User, UserRole
from app.models.voice import VoiceEvent, VoiceSession
from app.schemas.channel import ChannelAccountRead
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
from app.voice.realtime_client import OpenAIRealtimeClient, RealtimeVoiceError
from app.voice.twilio_bridge import TwilioMediaBridge
from app.voice.twilio_protocol import (
    TWILIO_MEDIA_CHANNELS,
    TWILIO_MEDIA_ENCODING,
    TWILIO_MEDIA_SAMPLE_RATE,
    TwilioProtocolError,
    build_bidirectional_twiml,
)

router = APIRouter(prefix="/channels/voice", tags=["voice"])
TenantAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
ACCOUNT_PATTERN = r"^[A-Za-z0-9_.-]{1,200}$"


@router.get("/config")
async def voice_config() -> dict:
    return {
        "openai_realtime": {
            "model": settings.openai_realtime_model,
            "voice": settings.openai_realtime_voice,
            "server_transport": "websocket",
            "lab_audio_format": "audio/pcmu",
            "max_session_minutes": settings.voice_session_max_minutes,
            "function_calling_capable": True,
        },
        "twilio_media_streams": {
            "transport": "websocket",
            "bidirectional": "Connect/Stream",
            "encoding": TWILIO_MEDIA_ENCODING,
            "sample_rate_hz": TWILIO_MEDIA_SAMPLE_RATE,
            "channels": TWILIO_MEDIA_CHANNELS,
            "live_audio_bridge": "v0.10_lab",
            "barge_in": settings.voice_barge_in_enabled,
            "lab_mode": settings.voice_bridge_lab_enabled,
            "lab_transcript_injection": True,
            "production_pstn_connected": False,
            "production_signature_requirement": "X-Twilio-Signature (not simulated in v0.10 lab)",
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


@router.websocket("/twilio/media")
async def twilio_media_stream(websocket: WebSocket):
    """Bidirectional Twilio Media Streams protocol endpoint.

    v0.10 validates the bridge with a Twilio-compatible simulated client. The
    endpoint speaks real media/mark/clear messages and emits real PCMU audio
    produced by OpenAI Realtime. It does not claim a PSTN/Twilio account is
    connected during the lab smoke test.
    """
    await TwilioMediaBridge(websocket).run()


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
