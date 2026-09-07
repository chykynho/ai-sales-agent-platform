from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VoiceSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_sessions"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "provider_call_id", name="uq_voice_session_tenant_provider_call"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    runtime_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="mock")
    provider_call_id: Mapped[str] = mapped_column(String(300), nullable=False)
    transport: Mapped[str] = mapped_column(String(50), nullable=False, default="mock_realtime")
    external_thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    from_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing", index=True)
    realtime_model: Mapped[str] = mapped_column(String(100), nullable=False)
    voice: Mapped[str] = mapped_column(String(50), nullable=False)
    input_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    realtime_session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    realtime_response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class VoiceEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    voice_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
