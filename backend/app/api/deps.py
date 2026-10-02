"""FastAPI dependencies: current user extractor and security contexts."""

import uuid

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_session_token
from app.db.session import get_db
from app.models.user import User


async def get_current_user_optional(
    session_cookie: str | None = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Extract current user from session cookie or Bearer token header if present."""
    token: str | None = session_cookie
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    if not token:
        return None

    payload = verify_session_token(token)
    if not payload or "sub" not in payload:
        return None

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        return None

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """Dependency that enforces an authenticated user; raises 401 Unauthorized otherwise."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in with GitHub.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
