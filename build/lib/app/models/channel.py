from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ChannelAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_channel_account_provider_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    runtime_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="whatsapp")
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="meta_cloud")
    provider_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    business_account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outbound_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="mock")
    access_token_env: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ChannelEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "channel_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_channel_event_provider_event"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="meta_cloud")
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="whatsapp")
    provider_event_id: Mapped[str] = mapped_column(String(300), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="accepted", index=True)
    from_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
