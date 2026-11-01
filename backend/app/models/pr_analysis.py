"""PRAnalysis ORM Model representing pull request summaries and deterministic risk assessments."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository


class PRAnalysis(Base):
    """PRAnalysis entity persisting AI summary and deterministic risk analysis per pull request."""

    __tablename__ = "pr_analyses"
    __table_args__ = (
        UniqueConstraint("repo_id", "pr_number", name="uq_pr_analyses_repo_pr"),
        Index("ix_pr_analyses_repo_id", "repo_id"),
        Index("ix_pr_analyses_risk_level", "risk_level"),
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
    pr_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    summary_markdown: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        default="low",
        nullable=False,
    )  # low | medium | high
    risk_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    risk_reasons: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )
    files_analyzed: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    truncated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa.text("false"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="ok",
        server_default="ok",
        nullable=False,
    )  # ok | error
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="pr_analyses",
    )
