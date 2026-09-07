"""Add WhatsApp channel accounts and event audit for v0.8.

Revision ID: 0006_whatsapp_channel
Revises: 0005_tenant_saas_config
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_whatsapp_channel"
down_revision = "0005_tenant_saas_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("runtime_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False, server_default="whatsapp"),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="meta_cloud"),
        sa.Column("provider_account_id", sa.String(length=200), nullable=False),
        sa.Column("business_account_id", sa.String(length=200), nullable=True),
        sa.Column("display_phone_number", sa.String(length=100), nullable=True),
        sa.Column("outbound_mode", sa.String(length=30), nullable=False, server_default="mock"),
        sa.Column("access_token_env", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_account_id", name="uq_channel_account_provider_id"),
    )
    op.create_index("ix_channel_accounts_tenant_id", "channel_accounts", ["tenant_id"])

    op.create_table(
        "channel_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="meta_cloud"),
        sa.Column("channel", sa.String(length=30), nullable=False, server_default="whatsapp"),
        sa.Column("provider_event_id", sa.String(length=300), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False, server_default="text"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="accepted"),
        sa.Column("from_address", sa.String(length=100), nullable=True),
        sa.Column("to_address", sa.String(length=100), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("raw_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_channel_event_provider_event"),
    )
    op.create_index("ix_channel_events_tenant_id", "channel_events", ["tenant_id"])
    op.create_index("ix_channel_events_channel_account_id", "channel_events", ["channel_account_id"])
    op.create_index("ix_channel_events_conversation_id", "channel_events", ["conversation_id"])
    op.create_index("ix_channel_events_status", "channel_events", ["status"])


def downgrade() -> None:
    op.drop_table("channel_events")
    op.drop_table("channel_accounts")
