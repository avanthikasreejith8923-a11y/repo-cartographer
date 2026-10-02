"""User response and serialization schemas using Pydantic v2."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Base fields for User."""

    login: str
    name: str | None = None
    avatar_url: str | None = None
    email: str | None = None


class UserRead(UserBase):
    """Schema returned to client for current authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    github_id: int
    created_at: datetime
    updated_at: datetime


class UserInDB(UserRead):
    """Internal user schema containing encrypted token."""

    encrypted_access_token: str


class TokenPayload(BaseModel):
    """Decoded session JWT payload."""

    sub: str  # User UUID
    github_id: int
    login: str
    exp: int
    iat: int | None = None


class AuthStatusResponse(BaseModel):
    """Response structure for auth status and logout."""

    authenticated: bool
    user: UserRead | None = None
    message: str | None = None
