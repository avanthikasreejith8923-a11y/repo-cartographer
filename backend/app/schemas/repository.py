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
    created_at: datetime
    updated_at: datetime


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

