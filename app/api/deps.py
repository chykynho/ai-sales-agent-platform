from typing import Annotated
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.observability.context import bind_context

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_raw = payload.get("sub")
        tenant_id_raw = payload.get("tenant_id")
        if not user_id_raw or not tenant_id_raw:
            raise credentials_exception
        user_id = uuid.UUID(user_id_raw)
        tenant_id = uuid.UUID(tenant_id_raw)
    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    bind_context(tenant_id=str(user.tenant_id))
    return user


def require_roles(*allowed_roles: UserRole):
    async def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return dependency

CurrentUser = Annotated[User, Depends(get_current_user)]
