"""Pydantic schemas for Phase 5 intelligence features."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PRAnalysisResponse(BaseModel):
    """Schema for pull request summary and risk analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    pr_number: int
    summary_markdown: str | None = None
    risk_level: str
    risk_score: int
    risk_reasons: list[Any] = Field(default_factory=list)
    files_analyzed: int
    truncated: bool = False
    status: str
    error: str | None = None
    model: str | None = None
    created_at: datetime
    updated_at: datetime


class IssueAnalysisResponse(BaseModel):
    """Schema for categorized issue analysis record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    issue_number: int
    issue_type: str
    confidence: float
    reason: str
    analyzed_at: datetime


class DuplicateIssueItem(BaseModel):
    """Schema representing one issue in a duplicate pair."""

    number: int
    title: str
    html_url: str | None = None


class DuplicateIssuePair(BaseModel):
    """Schema representing a pair of detected duplicate issues."""

    issue_1: DuplicateIssueItem
    issue_2: DuplicateIssueItem
    similarity: float


class AnalysisJobResponse(BaseModel):
    """Schema for asynchronous intelligence analysis job status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    kind: str
    status: str
    stage: str
    progress: int
    error: str | None = None
    stats: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GenerateTestRequest(BaseModel):
    """Schema for requesting unit test generation for a source file."""

    path: str = Field(..., description="Repository-relative file path to generate tests for", examples=["app/core/security.py"])


class GeneratedTestResponse(BaseModel):
    """Schema for an AI-generated draft unit test."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repo_id: uuid.UUID
    path: str
    framework: str
    content: str
    syntax_valid: bool | None = None
    notes: str | None = None
    model: str | None = None
    indexed_commit_sha: str | None = None
    created_at: datetime
