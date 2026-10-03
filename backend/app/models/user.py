"""User ORM Model representing an authenticated GitHub user."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class User(Base, TimestampMixin):
    """User entity mapping to GitHub authenticated profile."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    github_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    login: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )
    encrypted_access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Relationships
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User login={self.login} github_id={self.github_id}>"
