import asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.tenant_config_service import TenantConfigService


async def bootstrap() -> None:
    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(select(Tenant).where(Tenant.name == settings.bootstrap_tenant_name))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name=settings.bootstrap_tenant_name, slug=settings.bootstrap_tenant_slug)
            db.add(tenant); await db.flush()
            print(f"[bootstrap] Tenant created: {tenant.name} ({tenant.id})")
        else:
            print(f"[bootstrap] Tenant already exists: {tenant.name} ({tenant.id})")

        user_result = await db.execute(select(User).where(User.tenant_id == tenant.id, User.email == settings.bootstrap_admin_email))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(tenant_id=tenant.id, email=settings.bootstrap_admin_email, full_name="Bootstrap Admin", hashed_password=hash_password(settings.bootstrap_admin_password), role=UserRole.ADMIN, is_active=True)
            db.add(user)
            print(f"[bootstrap] Admin created: {user.email}")
        else:
            print(f"[bootstrap] Admin already exists: {user.email}")

        service = TenantConfigService()
        tenants = list((await db.execute(select(Tenant))).scalars().all())
        for item in tenants:
            await service.ensure(db=db, tenant=item, company_name=item.name)
            await service.ensure_default_products(db=db, tenant_id=item.id)
        await db.commit()
        print(f"[bootstrap] SaaS config/catalog ensured for {len(tenants)} tenant(s)")


if __name__ == "__main__":
    asyncio.run(bootstrap())
