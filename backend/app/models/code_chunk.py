"""CodeChunk ORM Model representing an embedded and indexed chunk of code."""

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector as _BaseVector
from sqlalchemy import Computed, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base


class Vector(_BaseVector):
    """Vector column type supporting both asyncpg binary codecs and sync libpq."""

    cache_ok = True

    def bind_processor(self, dialect: Any) -> Any:
        if getattr(dialect, "driver", None) == "asyncpg":
            def process(val: Any) -> Any:
                if val is None:
                    return None
                if isinstance(val, str):
                    cleaned = val.strip("[] \t\n\r")
                    return [float(x) for x in cleaned.split(",")] if cleaned else []
                if hasattr(val, "tolist"):
                    return val.tolist()
                return list(val)

            return process
        return super().bind_processor(dialect)


if TYPE_CHECKING:
    from app.models.repo_file import RepoFile
    from app.models.repository import Repository


class CodeChunk(Base):
    """CodeChunk entity storing split code fragments, vector embeddings, and search vectors."""

    __tablename__ = "code_chunks"
    __table_args__ = (
        UniqueConstraint("file_id", "chunk_index", name="uq_code_chunks_file_chunk_index"),
        Index("ix_code_chunks_repo_id", "repo_id"),
        Index("ix_code_chunks_file_id", "file_id"),
        Index("ix_code_chunks_repo_path", "repo_id", "path"),
        Index("ix_code_chunks_content_hash", "content_hash"),
        Index(
            "ix_code_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_code_chunks_tsv",
            "tsv",
            postgresql_using="gin",
        ),
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
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repo_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    start_line: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    end_line: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # function | class | section | window
    symbol: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.EMBEDDING_DIM),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', content)", persisted=True),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship("Repository", back_populates="chunks")
    file: Mapped["RepoFile"] = relationship("RepoFile", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<CodeChunk #{self.chunk_index} {self.kind} ({self.path}:{self.start_line}-{self.end_line})>"
