from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.models.user import User, UserRole
from app.services.tenant_config_service import TenantConfigService


def parse_args():
    p = argparse.ArgumentParser(description="Idempotently provision one SaaS tenant")
    p.add_argument("--slug", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-password", required=True)
    p.add_argument("--company-name", required=True)
    p.add_argument("--assistant-name", default="Assistente")
    p.add_argument("--timezone", default="America/Sao_Paulo")
    p.add_argument("--locale", default="pt-BR")
    p.add_argument("--tone", default="professional")
    p.add_argument("--custom-instructions", default="")
    p.add_argument("--enabled-tools", default="check_price,get_customer_by_email,check_availability,search_knowledge,create_lead")
    p.add_argument("--rag-top-k", type=int, default=5)
    p.add_argument("--rag-min-similarity", default="0.15")
    p.add_argument("--price-starter", default="497.00")
    p.add_argument("--price-pro", default="997.00")
    p.add_argument("--price-enterprise", default="2497.00")
    return p.parse_args()


async def main():
    args = parse_args()
    enabled = [x.strip() for x in args.enabled_tools.split(",") if x.strip()]
    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == args.slug))).scalar_one_or_none()
        created = tenant is None
        if tenant is None:
            tenant = Tenant(name=args.name, slug=args.slug, is_active=True)
            db.add(tenant); await db.flush()
        else:
            tenant.name = args.name; tenant.is_active = True

        service = TenantConfigService()
        config = await service.ensure(
            db=db, tenant=tenant, company_name=args.company_name,
            assistant_name=args.assistant_name, locale=args.locale, timezone=args.timezone,
            tone=args.tone, custom_instructions=args.custom_instructions,
            enabled_tools=enabled, rag_top_k=args.rag_top_k,
            rag_min_similarity=Decimal(args.rag_min_similarity),
        )
        # Provisioning is authoritative: update an existing tenant to desired state.
        config.company_name=args.company_name; config.assistant_name=args.assistant_name
        config.locale=args.locale; config.timezone=args.timezone; config.tone=args.tone
        config.custom_instructions=args.custom_instructions; config.enabled_tools=service.normalize_tools(enabled)
        config.rag_top_k=args.rag_top_k; config.rag_min_similarity=Decimal(args.rag_min_similarity)
        if not created: config.config_version += 1

        user = (await db.execute(select(User).where(User.tenant_id == tenant.id, User.email == args.admin_email))).scalar_one_or_none()
        if user is None:
            user = User(tenant_id=tenant.id, email=args.admin_email, full_name=f"{args.company_name} Admin", hashed_password=hash_password(args.admin_password), role=UserRole.ADMIN, is_active=True)
            db.add(user)
        else:
            user.hashed_password=hash_password(args.admin_password); user.role=UserRole.ADMIN; user.is_active=True

        for code, name, price in [
            ("STARTER", "Plano Starter", Decimal(args.price_starter)),
            ("PRO", "Plano PRO", Decimal(args.price_pro)),
            ("ENTERPRISE", "Plano Enterprise", Decimal(args.price_enterprise)),
        ]:
            await service.upsert_product(db=db, tenant_id=tenant.id, code=code, name=name, description=None, currency="BRL", price=price, is_active=True, commit=False)
        await db.commit()
        print(json.dumps({"tenant_id": str(tenant.id), "slug": tenant.slug, "created": created, "admin_email": args.admin_email, "config_version": config.config_version, "enabled_tools": config.enabled_tools}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
