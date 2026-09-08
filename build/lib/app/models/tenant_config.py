from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.tenant_defaults import DEFAULT_BUSINESS_HOURS, DEFAULT_ENABLED_TOOLS


class TenantConfig(TimestampMixin, Base):
    __tablename__ = "tenant_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    assistant_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Assistente")
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="pt-BR")
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="America/Sao_Paulo")
    tone: Mapped[str] = mapped_column(String(50), nullable=False, default="professional")
    custom_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=lambda: list(DEFAULT_ENABLED_TOOLS))
    business_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: dict(DEFAULT_BUSINESS_HOURS))
    rag_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rag_min_similarity: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.1500"))
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TenantProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_products"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tenant_products_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
