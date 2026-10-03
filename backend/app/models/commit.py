"""Commit ORM Model representing an ingested git commit."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class Commit(Base, TimestampMixin):
    """Commit entity representing a git commit in a repository."""

    __tablename__ = "commits"
    __table_args__ = (
        UniqueConstraint("repo_id", "sha", name="uq_commits_repo_sha"),
        Index("ix_commits_repo_id", "repo_id"),
        Index("ix_commits_committed_at", "committed_at"),
        Index("ix_commits_author_login", "author_login"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    sha: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    author_login: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    author_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    additions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    deletions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    files_changed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="commits")

    def __repr__(self) -> str:
        return f"<Commit sha={self.sha[:7]} repo_id={self.repo_id}>"
