"""Repository ORM Model representing an imported GitHub repository."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.code_chunk import CodeChunk
    from app.models.commit import Commit
    from app.models.generated_test import GeneratedTest
    from app.models.index_job import IndexJob
    from app.models.issue import Issue
    from app.models.issue_analysis import IssueAnalysis
    from app.models.pr_analysis import PRAnalysis
    from app.models.pull_request import PullRequest
    from app.models.qa_history import QAHistory
    from app.models.repo_doc import RepoDoc
    from app.models.repo_file import RepoFile
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
    # Phase 3 Indexing attributes
    index_status: Mapped[str] = mapped_column(
        String(50),
        default="none",
        server_default="none",
        nullable=False,
        index=True,
    )  # none | indexing | ready | failed
    indexed_commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
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
    files: Mapped[list["RepoFile"]] = relationship(
        "RepoFile",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        "CodeChunk",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    index_jobs: Mapped[list["IndexJob"]] = relationship(
        "IndexJob",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(IndexJob.created_at)",
    )
    qa_histories: Mapped[list["QAHistory"]] = relationship(
        "QAHistory",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(QAHistory.created_at)",
    )
    docs: Mapped[list["RepoDoc"]] = relationship(
        "RepoDoc",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    pr_analyses: Mapped[list["PRAnalysis"]] = relationship(
        "PRAnalysis",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(PRAnalysis.created_at)",
    )
    issue_analyses: Mapped[list["IssueAnalysis"]] = relationship(
        "IssueAnalysis",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(IssueAnalysis.analyzed_at)",
    )
    generated_tests: Mapped[list["GeneratedTest"]] = relationship(
        "GeneratedTest",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(GeneratedTest.created_at)",
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="repository",
        cascade="all, delete-orphan",
        order_by="desc(AnalysisJob.created_at)",
    )

    @property
    def owner(self) -> str:
        """Extract repository owner login from full_name."""
        return self.full_name.split("/")[0] if "/" in self.full_name else ""

    @property
    def name(self) -> str:
        """Extract repository short name from full_name."""
        return self.full_name.split("/")[1] if "/" in self.full_name else self.full_name

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("index_status", "none")
        kw.setdefault("chunk_count", 0)
        super().__init__(**kw)

    def __repr__(self) -> str:
        return f"<Repository full_name={self.full_name} status={self.status} index_status={self.index_status}>"

