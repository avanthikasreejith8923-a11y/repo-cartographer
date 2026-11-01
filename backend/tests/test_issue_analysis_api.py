"""API tests for Issue Analysis and Duplicate Detection endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.analysis_job import AnalysisJob
from app.models.issue import Issue
from app.models.issue_analysis import IssueAnalysis
from app.models.repository import Repository
from app.models.user import User
from tests.conftest import InMemoryAsyncSession


def create_authenticated_user(fake_db: InMemoryAsyncSession, github_id: int = 888222) -> tuple[User, dict[str, str]]:
    """Helper to persist a test user and generate session cookies."""
    user = User(
        id=uuid.uuid4(),
        github_id=github_id,
        login=f"user_{github_id}",
        name=f"User {github_id}",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}
    return user, cookies


def create_repo_with_issues(
    user: User,
    fake_db: InMemoryAsyncSession,
    issue_count: int = 2,
) -> tuple[Repository, list[Issue]]:
    """Helper to persist a repo and issues."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=54321,
        full_name="testuser/issue-repo",
        default_branch="main",
        status="ready",
    )
    fake_db.add(repo)

    issues = []
    for i in range(1, issue_count + 1):
        iss = Issue(
            id=uuid.uuid4(),
            repo_id=repo.id,
            number=i,
            title=f"Sample Issue #{i}",
            body=f"Description for issue {i}",
            state="open",
            labels=[{"name": "bug"}] if i % 2 == 1 else [{"name": "feature"}],
            author_login="tester",
            created_at=datetime.now(UTC),
        )
        fake_db.add(iss)
        issues.append(iss)

    return repo, issues


@pytest.mark.asyncio
async def test_trigger_issue_analysis_no_issues_returns_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/issues/analyze returns 409 if repo has no synced issues."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_repo_with_issues(user, fake_db, issue_count=0)

    response = await client.post(
        f"/repos/{repo.id}/issues/analyze",
        cookies=cookies,
    )
    assert response.status_code == 409
    assert "no synced issues" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_issue_analysis_other_user_repo_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/issues/analyze returns 404 for other user's repository."""
    owner_user, _ = create_authenticated_user(fake_db, github_id=333)
    other_user, other_cookies = create_authenticated_user(fake_db, github_id=444)
    repo, _ = create_repo_with_issues(owner_user, fake_db, issue_count=2)

    response = await client.post(
        f"/repos/{repo.id}/issues/analyze",
        cookies=other_cookies,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_issue_analysis_success_and_conflict_when_running(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/issues/analyze triggers job and returns 409 if already running."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_repo_with_issues(user, fake_db, issue_count=3)

    with (
        patch("app.api.routes.repos.enqueue_issue_analysis_job", return_value="job-123"),
        patch("app.services.queue.worker_alive", return_value=True),
    ):
        # First trigger succeeds
        res1 = await client.post(f"/repos/{repo.id}/issues/analyze", cookies=cookies)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["kind"] == "issues"
        assert data1["status"] == "pending"

        # Update status to running in memory to simulate active worker
        job = fake_db.analysis_jobs_by_id[uuid.UUID(data1["id"])]
        job.status = "running"

        # Second trigger while running returns 409
        res2 = await client.post(f"/repos/{repo.id}/issues/analyze", cookies=cookies)
        assert res2.status_code == 409
        assert "already running" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_issue_analysis_status_and_stuck_job_expiration(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/issues/analysis-status returns status and expires stuck jobs when worker dead."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_repo_with_issues(user, fake_db, issue_count=2)

    # When no job exists:
    res_none = await client.get(f"/repos/{repo.id}/issues/analysis-status", cookies=cookies)
    assert res_none.status_code == 200
    assert res_none.json()["status"] == "none"

    # Add a job that has been pending for 3 minutes
    old_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    stuck_job = AnalysisJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        kind="issues",
        status="pending",
        stage="queued",
        progress=0,
        started_at=old_time,
        created_at=old_time,
    )
    fake_db.add(stuck_job)

    # When worker is not alive, GET analysis-status expires it
    with patch("app.services.queue.worker_alive", return_value=False):
        res_expired = await client.get(f"/repos/{repo.id}/issues/analysis-status", cookies=cookies)
        assert res_expired.status_code == 200
        data = res_expired.json()
        assert data["status"] == "failed"
        assert "background worker is not running" in data["error"]


@pytest.mark.asyncio
async def test_list_issue_analyses_pagination_and_filter(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/issues/analysis returns paginated records with optional type filter."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_repo_with_issues(user, fake_db, issue_count=3)

    # Seed analysis records
    ia1 = IssueAnalysis(
        id=uuid.uuid4(),
        repo_id=repo.id,
        issue_number=1,
        issue_type="bug",
        confidence=0.9,
        reason="Bug reason",
        analyzed_at=datetime.now(UTC),
    )
    ia2 = IssueAnalysis(
        id=uuid.uuid4(),
        repo_id=repo.id,
        issue_number=2,
        issue_type="feature",
        confidence=0.85,
        reason="Feature reason",
        analyzed_at=datetime.now(UTC),
    )
    fake_db.add(ia1)
    fake_db.add(ia2)

    # List all
    res_all = await client.get(f"/repos/{repo.id}/issues/analysis", cookies=cookies)
    assert res_all.status_code == 200
    assert len(res_all.json()) == 2

    # Filter by bug
    res_bug = await client.get(f"/repos/{repo.id}/issues/analysis?type=bug", cookies=cookies)
    assert res_bug.status_code == 200
    assert len(res_bug.json()) == 1
    assert res_bug.json()[0]["issue_type"] == "bug"


@pytest.mark.asyncio
async def test_get_duplicate_issues_endpoint(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/issues/duplicates returns duplicate issue pairs."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_repo_with_issues(user, fake_db, issue_count=2)

    # Seed duplicate embeddings
    emb = [1.0, 0.0, 0.0]
    ia1 = IssueAnalysis(
        id=uuid.uuid4(),
        repo_id=repo.id,
        issue_number=1,
        issue_type="bug",
        confidence=0.9,
        reason="",
        embedding=emb,
        analyzed_at=datetime.now(UTC),
    )
    ia2 = IssueAnalysis(
        id=uuid.uuid4(),
        repo_id=repo.id,
        issue_number=2,
        issue_type="bug",
        confidence=0.9,
        reason="",
        embedding=emb,
        analyzed_at=datetime.now(UTC),
    )
    fake_db.add(ia1)
    fake_db.add(ia2)

    response = await client.get(f"/repos/{repo.id}/issues/duplicates", cookies=cookies)
    assert response.status_code == 200
    pairs = response.json()
    assert len(pairs) == 1
    assert pairs[0]["similarity"] == 1.0
    assert pairs[0]["issue_1"]["number"] == 1
    assert pairs[0]["issue_2"]["number"] == 2
    assert "github.com" in pairs[0]["issue_1"]["html_url"]
