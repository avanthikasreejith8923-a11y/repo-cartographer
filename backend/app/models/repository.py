"""Repository ORM Model representing an imported GitHub repository."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.commit import Commit
    from app.models.issue import Issue
    from app.models.pull_request import PullRequest
    from app.models.sync_job import SyncJob
    from app.models.user import User


class Repository(Base, TimestampMixin):
    """Repository entity mapping to an imported GitHub project."""

    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("user_id", "github_id", name="uq_repositories_user_github"),
        Index("ix_repositories_user_id", "user_id"),
        Index("ix_repositories_github_id", "github_id"),
        Index("ix_repositories_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    default_branch: Mapped[str] = mapped_column(
        String(100),
        default="main",
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    is_private: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )  # pending | syncing | ready | failed
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="repositories")
    commits: Mapped[list["Commit"]] = relationship(
        "Commit",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(Commit.committed_at)",
    )
    pull_requests: Mapped[list["PullRequest"]] = relationship(
        "PullRequest",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(PullRequest.created_at)",
    )
    issues: Mapped[list["Issue"]] = relationship(
        "Issue",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(Issue.created_at)",
    )
    sync_jobs: Mapped[list["SyncJob"]] = relationship(
        "SyncJob",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(SyncJob.created_at)",
    )

    def __repr__(self) -> str:
        return f"<Repository full_name={self.full_name} status={self.status}>"
