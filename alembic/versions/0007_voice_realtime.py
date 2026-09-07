"""Add Realtime voice session audit for v0.9.

Revision ID: 0007_voice_realtime
Revises: 0006_whatsapp_channel
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_voice_realtime"
down_revision = "0006_whatsapp_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("runtime_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="mock"),
        sa.Column("provider_call_id", sa.String(300), nullable=False),
        sa.Column("transport", sa.String(50), nullable=False, server_default="mock_realtime"),
        sa.Column("external_thread_id", sa.String(100), nullable=False),
        sa.Column("from_address", sa.String(100), nullable=True),
        sa.Column("to_address", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="processing"),
        sa.Column("realtime_model", sa.String(100), nullable=False),
        sa.Column("voice", sa.String(50), nullable=False),
        sa.Column("input_transcript", sa.Text(), nullable=True),
        sa.Column("assistant_text", sa.Text(), nullable=True),
        sa.Column("audio_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_sha256", sa.String(64), nullable=True),
        sa.Column("realtime_session_id", sa.String(200), nullable=True),
        sa.Column("realtime_response_id", sa.String(200), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("session_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "provider", "provider_call_id", name="uq_voice_session_tenant_provider_call"),
    )
    op.create_index("ix_voice_sessions_tenant_id", "voice_sessions", ["tenant_id"])
    op.create_index("ix_voice_sessions_channel_account_id", "voice_sessions", ["channel_account_id"])
    op.create_index("ix_voice_sessions_conversation_id", "voice_sessions", ["conversation_id"])
    op.create_index("ix_voice_sessions_status", "voice_sessions", ["status"])

    op.create_table(
        "voice_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voice_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("voice_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("audio_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_voice_events_tenant_id", "voice_events", ["tenant_id"])
    op.create_index("ix_voice_events_voice_session_id", "voice_events", ["voice_session_id"])


def downgrade() -> None:
    op.drop_table("voice_events")
    op.drop_table("voice_sessions")
