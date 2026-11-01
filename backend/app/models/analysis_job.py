"""AnalysisJob ORM Model representing background analysis tasks (e.g. issue classification)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository


class AnalysisJob(Base):
    """AnalysisJob entity tracking lifecycle and progress of repository analysis tasks."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_repo_id", "repo_id"),
        Index("ix_analysis_jobs_status", "status"),
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
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # e.g. "issues"
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        server_default="pending",
        nullable=False,
    )  # pending | running | ready | failed
    stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
        back_populates="analysis_jobs",
    )
