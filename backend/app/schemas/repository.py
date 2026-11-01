"""Pydantic schemas for repositories and GitHub import operations."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AvailableRepoResponse(BaseModel):
    """Schema representing a GitHub repository available for import."""

    model_config = ConfigDict(from_attributes=True)

    github_id: int = Field(..., description="GitHub repository ID")
    name: str
    full_name: str
    description: str | None = None
    is_private: bool = False
    html_url: str | None = None
    default_branch: str = "main"
    language: str | None = None
    is_imported: bool = False


class RepoImportRequest(BaseModel):
    """Schema for repository import request."""

    full_name: str = Field(..., description="Full repository name in 'owner/repo' format", examples=["octocat/Hello-World"])

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if "/" not in v or len(v.split("/")) != 2 or not v.split("/")[0] or not v.split("/")[1]:
            raise ValueError("Repository full_name must be in 'owner/repo' format.")
        return v


class RepoResponse(BaseModel):
    """Schema for stored Repository details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    github_id: int
    full_name: str
    description: str | None = None
    default_branch: str = "main"
    language: str | None = None
    is_private: bool = False
    status: str
    last_synced_at: datetime | None = None
    sync_error: str | None = None
    index_status: str = "none"
    indexed_commit_sha: str | None = None
    indexed_at: datetime | None = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("index_status", mode="before")
    @classmethod
    def default_index_status(cls, v: Any) -> str:
        return v if v is not None else "none"

    @field_validator("chunk_count", mode="before")
    @classmethod
    def default_chunk_count(cls, v: Any) -> int:
        return v if v is not None else 0



class SyncJobResponse(BaseModel):
    """Schema for sync job status and progress."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    status: str
    stage: str
    progress: int
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class RepoImportResponse(BaseModel):
    """Response returned upon initiating a repository import."""

    repository: RepoResponse
    sync_job: SyncJobResponse | None = None


class CommitResponse(BaseModel):
    """Schema for stored Commit details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    sha: str
    author_login: str | None = None
    author_name: str | None = None
    message: str
    committed_at: datetime
    additions: int | None = None
    deletions: int | None = None
    files_changed: int | None = None
    created_at: datetime


class PullRequestResponse(BaseModel):
    """Schema for stored Pull Request details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    number: int
    title: str
    body: str | None = None
    state: str
    author_login: str | None = None
    created_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None
    base_ref: str | None = None
    head_ref: str | None = None


class IssueResponse(BaseModel):
    """Schema for stored Issue details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[dict[str, Any]] = Field(default_factory=list)
    author_login: str | None = None
    created_at: datetime
    closed_at: datetime | None = None


class IndexJobResponse(BaseModel):
    """Schema for indexing job status and progress."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    status: str
    stage: str
    progress: int
    error: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    @field_validator("stats", mode="before")
    @classmethod
    def default_stats(cls, v: Any) -> dict[str, Any]:
        return v if v is not None else {}


class CodeSearchRequest(BaseModel):
    """Schema for code search request."""

    query: str = Field(..., min_length=1, description="Code or natural language search query")
    mode: str = Field(
        default="hybrid",
        pattern="^(hybrid|semantic|keyword)$",
        description="Search mode: hybrid, semantic, keyword",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Max results to return")


class SearchResultResponse(BaseModel):
    """Schema for individual search result item."""

    id: uuid.UUID
    path: str
    start_line: int
    end_line: int
    language: str | None = None
    symbol: str | None = None
    kind: str
    score: float
    snippet: str
    permalink: str


class SourceCitationResponse(BaseModel):
    """Schema for cited source chunk reference with deep link."""

    marker: str
    path: str
    start_line: int
    end_line: int
    symbol: str | None = None
    language: str | None = None
    snippet: str
    permalink: str


class AskQuestionRequest(BaseModel):
    """Schema for codebase Q&A request."""

    question: str = Field(..., min_length=1, description="Question about the repository codebase")


class AskQuestionResponse(BaseModel):
    """Schema for codebase Q&A response with citations and metadata."""

    answer: str
    status: str
    citations_missing: bool
    sources: list[SourceCitationResponse]
    history_id: uuid.UUID | None = None
    latency_ms: int


class QAHistoryResponse(BaseModel):
    """Schema for persisted QAHistory records."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    user_id: uuid.UUID
    question: str
    answer: str
    citations: list[dict[str, Any]] | list[Any] = []
    status: str
    model: str
    indexed_commit_sha: str | None = None
    latency_ms: int
    created_at: datetime


class DocResponse(BaseModel):
    """Schema for generated documentation status, content, citations, and staleness."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    repo_id: uuid.UUID
    doc_type: str
    status: str
    content_markdown: str | None = None
    citations: list[dict[str, Any]] | list[Any] = Field(default_factory=list)
    error: str | None = None
    model: str | None = None
    indexed_commit_sha: str | None = None
    is_stale: bool = False
    generated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("citations", mode="before")
    @classmethod
    def ensure_citations_list(cls, v: Any) -> list:
        return v if v is not None else []



