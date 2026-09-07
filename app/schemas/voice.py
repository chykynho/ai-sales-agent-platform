from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VoiceAccountUpsert(BaseModel):
    account_sid: str | None = Field(default=None, max_length=200)
    display_phone_number: str | None = Field(default=None, max_length=100)
    outbound_mode: Literal["mock", "twilio_media_stream"] = "mock"
    access_token_env: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    is_active: bool = True


class RealtimeProbeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class RealtimeProbeResponse(BaseModel):
    model: str
    session_id: str | None
    response_id: str | None
    text: str
    event_count: int
    latency_ms: int
    usage: dict[str, Any]


class MockVoiceTurnRequest(BaseModel):
    provider_call_id: str = Field(min_length=3, max_length=300, pattern=r"^[A-Za-z0-9_.:+-]+$")
    from_address: str = Field(min_length=3, max_length=100)
    transcript: str = Field(min_length=1, max_length=4000)


class VoiceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_account_id: uuid.UUID
    runtime_user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    provider: str
    provider_call_id: str
    transport: str
    external_thread_id: str
    from_address: str | None
    to_address: str | None
    status: str
    realtime_model: str
    voice: str
    input_transcript: str | None
    assistant_text: str | None
    audio_bytes: int
    audio_sha256: str | None
    realtime_session_id: str | None
    realtime_response_id: str | None
    latency_ms: int | None
    session_metadata: dict
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class VoiceEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    voice_session_id: uuid.UUID
    direction: str
    event_type: str
    status: str
    transcript: str | None
    audio_bytes: int
    event_metadata: dict
    created_at: datetime
    updated_at: datetime


class MockVoiceTurnResponse(BaseModel):
    deduplicated: bool
    session: VoiceSessionRead
    realtime_audio_transcript: str
