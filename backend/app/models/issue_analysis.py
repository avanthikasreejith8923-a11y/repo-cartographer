"""IssueAnalysis ORM Model representing issue classification and pgvector embeddings."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base
from app.models.code_chunk import Vector

if TYPE_CHECKING:
    from app.models.repository import Repository


class IssueAnalysis(Base):
    """IssueAnalysis entity persisting LLM classification and embedding vector per issue."""

    __tablename__ = "issue_analyses"
    __table_args__ = (
        UniqueConstraint("repo_id", "issue_number", name="uq_issue_analyses_repo_issue"),
        Index("ix_issue_analyses_repo_id", "repo_id"),
        Index("ix_issue_analyses_issue_type", "issue_type"),
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
    issue_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    issue_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # bug | feature | question | documentation | chore | unclassified
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIM),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="issue_analyses",
    )
