"""IndexJob ORM Model representing an asynchronous repository indexing task."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.repository import Repository


class IndexJob(Base, TimestampMixin):
    """IndexJob entity tracking the lifecycle, stages, and metrics of codebase indexing."""

    __tablename__ = "index_jobs"
    __table_args__ = (
        Index("ix_index_jobs_repo_id", "repo_id"),
        Index("ix_index_jobs_status", "status"),
        Index("ix_index_jobs_created_at", "created_at"),
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
    )  # pending | running | ready | failed
    stage: Mapped[str] = mapped_column(
        String(50),
        default="queued",
        nullable=False,
    )  # queued | fetching | filtering | chunking | embedding | saving | ready | failed
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )  # 0 to 100 percentage
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )  # files_seen, files_indexed, files_skipped, chunks_created, chunks_embedded
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="index_jobs")

    def __repr__(self) -> str:
        return f"<IndexJob id={self.id} status={self.status} stage={self.stage} progress={self.progress}%>"
