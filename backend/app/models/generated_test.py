"""GeneratedTest ORM Model representing AI-generated unit test drafts."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.user import User


class GeneratedTest(Base):
    """GeneratedTest entity persisting unit test generation drafts and syntax status."""

    __tablename__ = "generated_tests"
    __table_args__ = (
        Index("ix_generated_tests_repo_path_created", "repo_id", "path", "created_at"),
        Index("ix_generated_tests_repo_id", "repo_id"),
        Index("ix_generated_tests_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    framework: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    syntax_valid: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    indexed_commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="generated_tests",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="generated_tests",
    )
