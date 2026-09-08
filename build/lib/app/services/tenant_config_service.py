from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig, TenantProduct
from app.core.tenant_defaults import DEFAULT_BUSINESS_HOURS, DEFAULT_ENABLED_TOOLS, KNOWN_TOOL_NAMES

DEFAULT_PRODUCTS = (
    ("STARTER", "Plano Starter", Decimal("497.00")),
    ("PRO", "Plano PRO", Decimal("997.00")),
    ("ENTERPRISE", "Plano Enterprise", Decimal("2497.00")),
)


class TenantConfigService:
    async def get(self, *, db: AsyncSession, tenant_id: uuid.UUID) -> TenantConfig:
        result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
        config = result.scalar_one_or_none()
        if config is None:
            tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
            config = await self.ensure(db=db, tenant=tenant)
            await db.commit()
            await db.refresh(config)
        return config

    async def ensure(
        self,
        *,
        db: AsyncSession,
        tenant: Tenant,
        company_name: str | None = None,
        assistant_name: str = "Assistente",
        locale: str = "pt-BR",
        timezone: str = "America/Sao_Paulo",
        tone: str = "professional",
        custom_instructions: str = "",
        enabled_tools: list[str] | None = None,
        business_hours: dict | None = None,
        rag_top_k: int = 5,
        rag_min_similarity: Decimal = Decimal("0.1500"),
    ) -> TenantConfig:
        result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
        config = result.scalar_one_or_none()
        if config is None:
            config = TenantConfig(
                tenant_id=tenant.id,
                company_name=company_name or tenant.name,
                assistant_name=assistant_name,
                locale=locale,
                timezone=timezone,
                tone=tone,
                custom_instructions=custom_instructions,
                enabled_tools=self.normalize_tools(enabled_tools if enabled_tools is not None else list(DEFAULT_ENABLED_TOOLS)),
                business_hours=business_hours or dict(DEFAULT_BUSINESS_HOURS),
                rag_top_k=rag_top_k,
                rag_min_similarity=rag_min_similarity,
                config_version=1,
            )
            db.add(config)
            await db.flush()
        return config

    async def ensure_default_products(self, *, db: AsyncSession, tenant_id: uuid.UUID) -> None:
        for code, name, price in DEFAULT_PRODUCTS:
            existing = (await db.execute(select(TenantProduct).where(
                TenantProduct.tenant_id == tenant_id,
                TenantProduct.code == code,
            ))).scalar_one_or_none()
            if existing is None:
                db.add(TenantProduct(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    currency="BRL",
                    price=price,
                    is_active=True,
                ))
        await db.flush()

    @staticmethod
    def normalize_tools(tools: list[str]) -> list[str]:
        unknown = sorted(set(tools) - set(KNOWN_TOOL_NAMES))
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        requested = set(tools)
        return [name for name in KNOWN_TOOL_NAMES if name in requested]

    async def list_products(self, *, db: AsyncSession, tenant_id: uuid.UUID) -> list[TenantProduct]:
        result = await db.execute(
            select(TenantProduct)
            .where(TenantProduct.tenant_id == tenant_id)
            .order_by(TenantProduct.code.asc())
        )
        return list(result.scalars().all())

    async def upsert_product(
        self,
        *,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        description: str | None,
        currency: str,
        price: Decimal,
        is_active: bool,
        commit: bool = True,
    ) -> TenantProduct:
        normalized = code.strip().upper()
        product = (await db.execute(select(TenantProduct).where(
            TenantProduct.tenant_id == tenant_id,
            TenantProduct.code == normalized,
        ))).scalar_one_or_none()
        if product is None:
            product = TenantProduct(tenant_id=tenant_id, code=normalized)
            db.add(product)
        product.name = name
        product.description = description
        product.currency = currency.strip().upper()
        product.price = price
        product.is_active = is_active
        if commit:
            await db.commit()
            await db.refresh(product)
        else:
            await db.flush()
        return product

    @staticmethod
    def tool_instructions(config: TenantConfig) -> str:
        extra = config.custom_instructions.strip()
        return (
            f"Você é {config.assistant_name}, agente comercial de {config.company_name}. "
            f"Responda no locale {config.locale}, com tom {config.tone}. "
            "Use ferramentas quando precisar consultar dados ou executar ações. "
            "Nunca invente preço, cliente, disponibilidade, políticas, conteúdo documental ou confirmação de criação. "
            "Para políticas, implantação, documentação ou conhecimento do cliente, use search_knowledge quando essa ferramenta estiver disponível. "
            "Somente afirme que uma ação ocorreu depois de receber o resultado da ferramenta. "
            + (f"Instruções específicas do tenant: {extra}" if extra else "")
        )

    @staticmethod
    def direct_instructions(config: TenantConfig) -> str:
        extra = config.custom_instructions.strip()
        return (
            f"Você é {config.assistant_name}, agente comercial de {config.company_name}. "
            f"Responda no locale {config.locale}, com tom {config.tone}, de forma objetiva. "
            "Use o histórico somente como contexto. Não invente preços, disponibilidade, clientes ou ações executadas. "
            + (f"Instruções específicas do tenant: {extra}" if extra else "")
        )
