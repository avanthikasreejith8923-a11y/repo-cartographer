"""QAHistory ORM Model representing codebase question answering records."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.user import User


class QAHistory(Base):
    """QAHistory entity persisting questions, answers, citations, and metrics."""

    __tablename__ = "qa_history"
    __table_args__ = (
        Index("ix_qa_history_repo_id", "repo_id"),
        Index("ix_qa_history_user_id", "user_id"),
        Index("ix_qa_history_repo_user_created", "repo_id", "user_id", "created_at"),
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="ok",
        nullable=False,
    )  # ok | insufficient_evidence | error
    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    indexed_commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository",
        back_populates="qa_histories",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="qa_histories",
    )
