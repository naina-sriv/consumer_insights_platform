import uuid
from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_UNAUTHORIZED_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"error": {"code": "unauthorized", "message": "Could not validate credentials"}},
    headers={"WWW-Authenticate": "Bearer"},
)


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    role: str


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Validate JWT access token and return active authenticated user."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        token_data = TokenPayload(**payload)
        user_uuid = uuid.UUID(token_data.sub)
        tenant_uuid = uuid.UUID(token_data.tenant_id)
    except (jwt.PyJWTError, ValidationError, ValueError):
        raise _UNAUTHORIZED_EXCEPTION

    query = select(User).where(
        User.id == user_uuid,
        User.tenant_id == tenant_uuid,
    )
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if user is None:
        raise _UNAUTHORIZED_EXCEPTION

    return user


def require_role(*allowed_roles: str) -> Callable[..., User]:
    """Dependency factory checking if current user possesses one of the required roles."""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "forbidden", "message": "Insufficient permissions"}},
            )
        return current_user

    return role_checker
