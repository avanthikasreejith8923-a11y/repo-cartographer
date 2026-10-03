"""SyncJob ORM Model representing an asynchronous repository synchronization job."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class SyncJob(Base, TimestampMixin):
    """SyncJob entity tracking the lifecycle and progress of repository ingestion."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_repo_id", "repo_id"),
        Index("ix_sync_jobs_status", "status"),
        Index("ix_sync_jobs_created_at", "created_at"),
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
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )  # pending | running | completed | failed
    stage: Mapped[str] = mapped_column(
        String(50),
        default="queued",
        nullable=False,
    )  # queued | metadata | commits | pull_requests | issues | completed | failed
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )  # 0 to 100 percentage
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="sync_jobs")

    def __repr__(self) -> str:
        return f"<SyncJob id={self.id} status={self.status} stage={self.stage} progress={self.progress}%>"
