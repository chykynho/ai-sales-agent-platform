"""Add tool calling audit and leads for v0.3.

Revision ID: 0003_tools
Revises: 0002_agent_runs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_tools"
down_revision: Union[str, None] = "0002_agent_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("provider_response_count", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("agent_runs", sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "leads",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("interest", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="new"),
        sa.Column("source", sa.String(50), nullable=False, server_default="ai_agent"),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_lead_tenant_idempotency"),
    )
    op.create_index("ix_leads_tenant_id", "leads", ["tenant_id"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "tool_calls",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_call_id", sa.String(200), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("is_write_action", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("arguments_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_calls_tenant_id", "tool_calls", ["tenant_id"])
    op.create_index("ix_tool_calls_agent_run_id", "tool_calls", ["agent_run_id"])
    op.create_index("ix_tool_calls_user_id", "tool_calls", ["user_id"])
    op.create_index("ix_tool_calls_tool_name", "tool_calls", ["tool_name"])
    op.create_index("ix_tool_calls_status", "tool_calls", ["status"])
    op.create_index("ix_tool_calls_idempotency_key", "tool_calls", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_idempotency_key", table_name="tool_calls")
    op.drop_index("ix_tool_calls_status", table_name="tool_calls")
    op.drop_index("ix_tool_calls_tool_name", table_name="tool_calls")
    op.drop_index("ix_tool_calls_user_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_agent_run_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_tenant_id", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_tenant_id", table_name="leads")
    op.drop_table("leads")
    op.drop_column("agent_runs", "tool_call_count")
    op.drop_column("agent_runs", "provider_response_count")
