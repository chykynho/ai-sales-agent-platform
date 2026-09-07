"""Add configurable SaaS tenant profile and product catalog for v0.7."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_tenant_saas_config"
down_revision = "0004_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_configs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("assistant_name", sa.String(length=100), nullable=False, server_default="Assistente"),
        sa.Column("locale", sa.String(length=20), nullable=False, server_default="pt-BR"),
        sa.Column("timezone", sa.String(length=100), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("tone", sa.String(length=50), nullable=False, server_default="professional"),
        sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("""'["check_price","get_customer_by_email","check_availability","search_knowledge","create_lead"]'::jsonb""")),
        sa.Column("business_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("""'{"weekdays":[0,1,2,3,4],"start":"09:00","end":"17:00"}'::jsonb""")),
        sa.Column("rag_top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("rag_min_similarity", sa.Numeric(5,4), nullable=False, server_default="0.1500"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenant_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="BRL"),
        sa.Column("price", sa.Numeric(12,2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_products_tenant_code"),
    )
    op.create_index("ix_tenant_products_tenant_id", "tenant_products", ["tenant_id"])
    # Existing tenants get a profile during migration. Product catalog is seeded by the
    # idempotent bootstrap immediately after migrations, avoiding UUID generation in DDL.
    op.execute("""
        INSERT INTO tenant_configs (tenant_id, company_name)
        SELECT id, name FROM tenants
        ON CONFLICT (tenant_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_tenant_products_tenant_id", table_name="tenant_products")
    op.drop_table("tenant_products")
    op.drop_table("tenant_configs")
