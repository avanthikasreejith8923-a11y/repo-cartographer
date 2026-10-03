"""PullRequest ORM Model representing an ingested GitHub pull request."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository


class PullRequest(Base):
    """PullRequest entity representing a pull request in a repository."""

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_pull_requests_repo_number"),
        Index("ix_pull_requests_repo_id", "repo_id"),
        Index("ix_pull_requests_created_at", "created_at"),
        Index("ix_pull_requests_state", "state"),
        Index("ix_pull_requests_author_login", "author_login"),
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
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # open | closed
    author_login: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    merged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    additions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    deletions: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    changed_files: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    base_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    head_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="pull_requests")

    def __repr__(self) -> str:
        return f"<PullRequest #{self.number} {self.state} repo_id={self.repo_id}>"
