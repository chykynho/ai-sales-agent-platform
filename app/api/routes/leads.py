from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.models.lead import Lead
from app.schemas.lead import LeadRead

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[LeadRead])
async def list_leads(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: str | None = Query(default=None, max_length=320),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[Lead]:
    stmt = select(Lead).where(Lead.tenant_id == current_user.tenant_id)
    if email:
        stmt = stmt.where(Lead.email == email)
    result = await db.execute(stmt.order_by(Lead.created_at.desc()).limit(limit))
    return list(result.scalars().all())
