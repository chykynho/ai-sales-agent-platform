from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.tenant_config import (
    TenantConfigRead,
    TenantConfigUpdate,
    TenantProductRead,
    TenantProductUpsert,
)
from app.services.tenant_config_service import TenantConfigService

router = APIRouter(prefix="/tenant", tags=["tenant-configuration"])
TenantAdmin = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


@router.get("/config", response_model=TenantConfigRead)
async def get_config(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    return await TenantConfigService().get(db=db, tenant_id=current_user.tenant_id)


@router.patch("/config", response_model=TenantConfigRead)
async def update_config(
    payload: TenantConfigUpdate,
    current_user: TenantAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    service = TenantConfigService()
    config = await service.get(db=db, tenant_id=current_user.tenant_id)
    changes = payload.model_dump(exclude_unset=True)
    if "enabled_tools" in changes and changes["enabled_tools"] is not None:
        changes["enabled_tools"] = service.normalize_tools(changes["enabled_tools"])
    if "business_hours" in changes and changes["business_hours"] is not None:
        value = changes["business_hours"]
        changes["business_hours"] = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    changed = False
    for key, value in changes.items():
        if value is not None and getattr(config, key) != value:
            setattr(config, key, value)
            changed = True
    if changed:
        config.config_version += 1
        await db.commit()
        await db.refresh(config)
    return config


@router.get("/products", response_model=list[TenantProductRead])
async def list_products(current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    return await TenantConfigService().list_products(db=db, tenant_id=current_user.tenant_id)


@router.put("/products/{code}", response_model=TenantProductRead)
async def upsert_product(
    payload: TenantProductUpsert,
    current_user: TenantAdmin,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,50}$")],
):
    return await TenantConfigService().upsert_product(
        db=db,
        tenant_id=current_user.tenant_id,
        code=code,
        name=payload.name,
        description=payload.description,
        currency=payload.currency,
        price=payload.price,
        is_active=payload.is_active,
    )
