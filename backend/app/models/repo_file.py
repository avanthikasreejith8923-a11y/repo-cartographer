"""RepoFile ORM Model representing an ingested file in a repository."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.code_chunk import CodeChunk
    from app.models.repository import Repository


class RepoFile(Base):
    """RepoFile entity tracking indexed files and content hashes for incremental indexing."""

    __tablename__ = "repo_files"
    __table_args__ = (
        UniqueConstraint("repo_id", "path", name="uq_repo_files_repo_path"),
        Index("ix_repo_files_repo_id", "repo_id"),
        Index("ix_repo_files_path", "path"),
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
    path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="files")
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RepoFile path={self.path} repo_id={self.repo_id}>"
