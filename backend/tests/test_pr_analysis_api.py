"""API tests for Pull Request Analysis endpoints using FakeLLMProvider."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.pr_analysis import PRAnalysis
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.user import User
from app.services.llm import FakeLLMProvider
from tests.conftest import InMemoryAsyncSession


def create_authenticated_user(fake_db: InMemoryAsyncSession, github_id: int = 777111) -> tuple[User, dict[str, str]]:
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


def create_repo_and_pr(user: User, fake_db: InMemoryAsyncSession, pr_number: int = 10) -> tuple[Repository, PullRequest]:
    """Helper to persist a repo and an associated pull request."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=98765,
        full_name="testuser/demo-repo",
        default_branch="main",
        status="ready",
    )
    fake_db.add(repo)

    pr = PullRequest(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=pr_number,
        title="Refactor auth middleware and update package.json",
        body="This PR updates security headers and dependency configurations.",
        state="open",
        author_login="contributor",
    )
    fake_db.add(pr)
    return repo, pr


@pytest.mark.asyncio
async def test_analyze_pull_request_success(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/pulls/{number}/analyze returns summary, risk level, and reasons."""
    user, cookies = create_authenticated_user(fake_db)
    repo, pr = create_repo_and_pr(user, fake_db, pr_number=10)

    fake_files = [
        {"filename": "app/core/security.py", "status": "modified", "additions": 20, "deletions": 5, "patch": "+# auth update"},
        {"filename": "package.json", "status": "modified", "additions": 2, "deletions": 1, "patch": '+  "lodash": "^4.17.21"'},
    ]

    with (
        patch("app.services.pr_analysis.get_llm_provider", return_value=FakeLLMProvider(mode="pr_summary")),
        patch("app.services.github_client.GitHubClient.list_pull_request_files", new_callable=AsyncMock) as mock_files,
    ):
        mock_files.return_value = fake_files
        response = await client.post(
            f"/repos/{repo.id}/pulls/10/analyze",
            cookies=cookies,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pr_number"] == 10
        assert data["status"] == "ok"
        assert data["risk_score"] > 0
        assert data["risk_level"] in ("medium", "high")
        assert len(data["risk_reasons"]) >= 1
        assert "Summary of Changes" in data["summary_markdown"]


@pytest.mark.asyncio
async def test_analyze_pull_request_cached_and_refresh(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """Verify caching: second call returns cached analysis unless refresh=true."""
    user, cookies = create_authenticated_user(fake_db)
    repo, pr = create_repo_and_pr(user, fake_db, pr_number=11)

    fake_files = [{"filename": "docs/readme.md", "status": "modified", "additions": 1, "deletions": 0, "patch": "+text"}]

    with (
        patch("app.services.pr_analysis.get_llm_provider", return_value=FakeLLMProvider(mode="pr_summary")),
        patch("app.services.github_client.GitHubClient.list_pull_request_files", new_callable=AsyncMock) as mock_files,
    ):
        mock_files.return_value = fake_files

        # First call: triggers analysis
        res1 = await client.post(f"/repos/{repo.id}/pulls/11/analyze", cookies=cookies)
        assert res1.status_code == 200
        assert mock_files.call_count == 1

        # Second call without refresh: returns cached, no GitHub call
        res2 = await client.post(f"/repos/{repo.id}/pulls/11/analyze", cookies=cookies)
        assert res2.status_code == 200
        assert mock_files.call_count == 1

        # Third call with refresh=true: re-analyzes, calls GitHub again
        res3 = await client.post(f"/repos/{repo.id}/pulls/11/analyze?refresh=true", cookies=cookies)
        assert res3.status_code == 200
        assert mock_files.call_count == 2


@pytest.mark.asyncio
async def test_analyze_pull_request_other_user_repo_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/pulls/{number}/analyze returns 404 for repositories owned by other users."""
    owner_user, _ = create_authenticated_user(fake_db, github_id=111)
    other_user, other_cookies = create_authenticated_user(fake_db, github_id=222)
    repo, _ = create_repo_and_pr(owner_user, fake_db, pr_number=12)

    response = await client.post(
        f"/repos/{repo.id}/pulls/12/analyze",
        cookies=other_cookies,
    )
    assert response.status_code == 404
    assert "Repository not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_analyze_pull_request_rate_limit_exceeded_returns_429(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/pulls/{number}/analyze returns 429 when rate limit exceeded."""
    user, cookies = create_authenticated_user(fake_db)
    repo, pr = create_repo_and_pr(user, fake_db, pr_number=13)

    from fastapi import HTTPException
    with patch("app.services.pr_analysis.check_rate_limit", side_effect=HTTPException(status_code=429, detail="Rate limit exceeded.")):
        response = await client.post(
            f"/repos/{repo.id}/pulls/13/analyze",
            cookies=cookies,
        )
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_pull_request_analysis_and_list_analyses(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """Test GET /repos/{id}/pulls/{number}/analysis and GET /repos/{id}/pulls/analyses."""
    user, cookies = create_authenticated_user(fake_db)
    repo, pr = create_repo_and_pr(user, fake_db, pr_number=14)

    # 404 when not analyzed yet
    res_not_found = await client.get(f"/repos/{repo.id}/pulls/14/analysis", cookies=cookies)
    assert res_not_found.status_code == 404

    # Seed an analysis record directly
    analysis = PRAnalysis(
        id=uuid.uuid4(),
        repo_id=repo.id,
        pr_number=14,
        summary_markdown="Summary text",
        risk_level="medium",
        risk_score=35,
        risk_reasons=["Some reason"],
        files_analyzed=3,
        truncated=False,
        status="ok",
    )
    fake_db.add(analysis)

    # Now GET single analysis succeeds
    res_ok = await client.get(f"/repos/{repo.id}/pulls/14/analysis", cookies=cookies)
    assert res_ok.status_code == 200
    assert res_ok.json()["risk_level"] == "medium"
    assert res_ok.json()["risk_score"] == 35

    # GET list of analyses
    res_list = await client.get(f"/repos/{repo.id}/pulls/analyses", cookies=cookies)
    assert res_list.status_code == 200
    analyses = res_list.json()
    assert len(analyses) == 1
    assert analyses[0]["pr_number"] == 14
