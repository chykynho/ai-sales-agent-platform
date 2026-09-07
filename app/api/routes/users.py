from typing import Annotated
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["users"])


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> User:
    return current_user


@router.get("", response_model=list[UserRead])
async def list_users(
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id).order_by(User.email.asc())
    )
    return list(result.scalars().all())
