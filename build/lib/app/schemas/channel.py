from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhatsAppAccountUpsert(BaseModel):
    business_account_id: str | None = Field(default=None, max_length=200)
    display_phone_number: str | None = Field(default=None, max_length=100)
    outbound_mode: Literal["mock", "meta_cloud"] = "mock"
    access_token_env: str | None = Field(default=None, max_length=200, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    is_active: bool = True

    @field_validator("access_token_env")
    @classmethod
    def require_env_for_real_mode(cls, value: str | None, info):
        # Cross-field enforcement is also repeated in the API after model parsing.
        return value


class ChannelAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    runtime_user_id: uuid.UUID
    channel: str
    provider: str
    provider_account_id: str
    business_account_id: str | None
    display_phone_number: str | None
    outbound_mode: str
    access_token_env: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ChannelEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    channel_account_id: uuid.UUID
    conversation_id: uuid.UUID | None
    provider: str
    channel: str
    provider_event_id: str
    direction: str
    event_type: str
    status: str
    from_address: str | None
    to_address: str | None
    content_text: str | None
    raw_payload_hash: str | None
    event_metadata: dict
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WhatsAppWebhookAcceptResponse(BaseModel):
    status: str = "accepted"
    accepted: int = 0
    duplicate: int = 0
    ignored: int = 0
