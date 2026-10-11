"""Integration tests for the repository synchronization pipeline against isolated TEST_DATABASE_URL.

Verifies:
1. Double-sync idempotency: running sync twice against live PostgreSQL gives identical row counts.
2. PR exclusion: GitHub issues that are actually pull requests are excluded from the issues table.
3. Access control: querying another user's repo returns 404.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.commit import Commit
from app.models.issue import Issue
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.services.sync_service import execute_repo_sync

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _make_mock_user(login: str, github_id: int) -> User:
    return User(
        id=uuid.uuid4(),
        github_id=github_id,
        login=login,
        name=f"Test {login}",
        email=f"{login}@example.com",
        avatar_url="https://avatars.githubusercontent.com/u/1?v=4",
        encrypted_access_token=encrypt_token("ghp_test_token_for_integration_testing_12345"),
    )


def _make_mock_repo(user_id: uuid.UUID, full_name: str, github_id: int) -> Repository:
    return Repository(
        id=uuid.uuid4(),
        user_id=user_id,
        github_id=github_id,
        full_name=full_name,
        description="Integration test repo",
        default_branch="main",
        status="pending",
        index_status="none",
        chunk_count=0,
    )


async def _cleanup_test_repo(session: AsyncSession, repo_id: uuid.UUID) -> None:
    """Cascade delete repository and all associated records."""
    await session.execute(delete(Commit).where(Commit.repo_id == repo_id))
    await session.execute(delete(PullRequest).where(PullRequest.repo_id == repo_id))
    await session.execute(delete(Issue).where(Issue.repo_id == repo_id))
    await session.execute(delete(SyncJob).where(SyncJob.repo_id == repo_id))
    await session.execute(delete(Repository).where(Repository.id == repo_id))
    await session.commit()


@respx.mock
async def test_sync_pipeline_idempotency_double_run(test_db_session: AsyncSession) -> None:
    """Verify that syncing a repository twice leaves identical row counts in PostgreSQL."""
    # 1. Setup User and Repository in test database
    user = _make_mock_user("sync-idempotency-user", 990011)
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "test-owner/idempotent-repo", 880011)
    test_db_session.add(repo)
    await test_db_session.commit()

    try:
        # 2. Mock GitHub API responses
        mock_meta = {
            "id": 880011,
            "full_name": "test-owner/idempotent-repo",
            "description": "Idempotency test repository",
            "default_branch": "main",
            "language": "Python",
            "private": False,
        }
        mock_commits = [
            {
                "sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "commit": {
                    "message": "feat: initial commit",
                    "author": {"name": "Dev One", "date": "2026-01-01T10:00:00Z"},
                },
                "author": {"login": "devone"},
            },
            {
                "sha": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
                "commit": {
                    "message": "fix: bugfix commit",
                    "author": {"name": "Dev Two", "date": "2026-01-02T12:00:00Z"},
                },
                "author": {"login": "devtwo"},
            },
        ]
        mock_commit_detail = {
            "stats": {"additions": 10, "deletions": 2, "total": 12},
            "files": [{"filename": "main.py"}],
        }
        mock_prs = [
            {
                "id": 1001,
                "number": 1,
                "title": "PR One",
                "state": "open",
                "user": {"login": "devone"},
                "created_at": "2026-01-01T10:00:00Z",
                "updated_at": "2026-01-02T10:00:00Z",
                "closed_at": None,
                "merged_at": None,
                "draft": False,
            }
        ]
        mock_pr_detail = {"additions": 15, "deletions": 5, "changed_files": 2}
        mock_issues = [
            {
                "id": 2001,
                "number": 10,
                "title": "First pure issue",
                "state": "open",
                "user": {"login": "devone"},
                "comments": 1,
                "labels": [{"name": "bug"}],
                "created_at": "2026-01-01T10:00:00Z",
                "updated_at": "2026-01-02T10:00:00Z",
                "closed_at": None,
            }
        ]

        respx.get("https://api.github.com/repos/test-owner/idempotent-repo").respond(200, json=mock_meta)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/commits").respond(200, json=mock_commits)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/commits/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2").respond(200, json=mock_commit_detail)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/commits/b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3").respond(200, json=mock_commit_detail)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/pulls").respond(200, json=mock_prs)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/pulls/1").respond(200, json=mock_pr_detail)
        respx.get("https://api.github.com/repos/test-owner/idempotent-repo/issues").respond(200, json=mock_issues)

        # 3. First execution
        await execute_repo_sync(repo_id=repo.id, db=test_db_session)

        count_commits_1 = (await test_db_session.execute(select(func.count(Commit.id)).where(Commit.repo_id == repo.id))).scalar()
        count_prs_1 = (await test_db_session.execute(select(func.count(PullRequest.id)).where(PullRequest.repo_id == repo.id))).scalar()
        count_issues_1 = (await test_db_session.execute(select(func.count(Issue.id)).where(Issue.repo_id == repo.id))).scalar()

        assert count_commits_1 == 2
        assert count_prs_1 == 1
        assert count_issues_1 == 1

        # 4. Second execution (must be completely idempotent)
        await execute_repo_sync(repo_id=repo.id, db=test_db_session)

        count_commits_2 = (await test_db_session.execute(select(func.count(Commit.id)).where(Commit.repo_id == repo.id))).scalar()
        count_prs_2 = (await test_db_session.execute(select(func.count(PullRequest.id)).where(PullRequest.repo_id == repo.id))).scalar()
        count_issues_2 = (await test_db_session.execute(select(func.count(Issue.id)).where(Issue.repo_id == repo.id))).scalar()

        assert count_commits_2 == count_commits_1, "Commits row count must remain identical after second sync"
        assert count_prs_2 == count_prs_1, "Pull Requests row count must remain identical after second sync"
        assert count_issues_2 == count_issues_1, "Issues row count must remain identical after second sync"

    finally:
        await _cleanup_test_repo(test_db_session, repo.id)
        await test_db_session.execute(delete(User).where(User.id == user.id))
        await test_db_session.commit()


@respx.mock
async def test_issues_ingestion_excludes_pull_requests(test_db_session: AsyncSession) -> None:
    """Verify that GitHub issues with 'pull_request' key are excluded from the issues table."""
    user = _make_mock_user("issues-filter-user", 990022)
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "test-owner/issues-filter-repo", 880022)
    test_db_session.add(repo)
    await test_db_session.commit()

    try:
        mock_meta = {
            "id": 880022,
            "full_name": "test-owner/issues-filter-repo",
            "description": "Issue filter test",
            "default_branch": "main",
            "language": "Python",
            "private": False,
        }
        # Mixture of 2 real issues and 2 PR-linked issues
        mock_mixed_issues = [
            {
                "id": 3001,
                "number": 1,
                "title": "Real Bug Report",
                "state": "open",
                "user": {"login": "reporter"},
                "comments": 2,
                "labels": [{"name": "bug"}],
                "created_at": "2026-01-01T10:00:00Z",
                "updated_at": "2026-01-02T10:00:00Z",
                "closed_at": None,
                # Pure issue: no pull_request key
            },
            {
                "id": 3002,
                "number": 2,
                "title": "Pull Request as Issue",
                "state": "open",
                "user": {"login": "pr-author"},
                "comments": 0,
                "labels": [],
                "created_at": "2026-01-01T11:00:00Z",
                "updated_at": "2026-01-02T11:00:00Z",
                "closed_at": None,
                "pull_request": {"url": "https://api.github.com/repos/test-owner/issues-filter-repo/pulls/2"},
            },
            {
                "id": 3003,
                "number": 3,
                "title": "Real Feature Request",
                "state": "closed",
                "user": {"login": "reporter2"},
                "comments": 4,
                "labels": [{"name": "enhancement"}],
                "created_at": "2026-01-01T12:00:00Z",
                "updated_at": "2026-01-02T12:00:00Z",
                "closed_at": "2026-01-02T12:00:00Z",
                "pull_request": None,  # Explicit None
            },
            {
                "id": 3004,
                "number": 4,
                "title": "Another Pull Request",
                "state": "closed",
                "user": {"login": "pr-author2"},
                "comments": 1,
                "labels": [],
                "created_at": "2026-01-01T13:00:00Z",
                "updated_at": "2026-01-02T13:00:00Z",
                "closed_at": "2026-01-02T13:00:00Z",
                "pull_request": {"html_url": "https://github.com/test-owner/issues-filter-repo/pull/4"},
            },
        ]

        respx.get("https://api.github.com/repos/test-owner/issues-filter-repo").respond(200, json=mock_meta)
        respx.get("https://api.github.com/repos/test-owner/issues-filter-repo/commits").respond(200, json=[])
        respx.get("https://api.github.com/repos/test-owner/issues-filter-repo/pulls").respond(200, json=[])
        respx.get("https://api.github.com/repos/test-owner/issues-filter-repo/issues").respond(200, json=mock_mixed_issues)

        await execute_repo_sync(repo_id=repo.id, db=test_db_session)

        # Query all ingested issues
        issues_res = await test_db_session.execute(
            select(Issue).where(Issue.repo_id == repo.id).order_by(Issue.number.asc())
        )
        ingested_issues = issues_res.scalars().all()

        assert len(ingested_issues) == 2, f"Expected exactly 2 pure issues, found {len(ingested_issues)}"
        ingested_numbers = [i.number for i in ingested_issues]
        assert ingested_numbers == [1, 3], f"Expected numbers [1, 3], found {ingested_numbers}"

    finally:
        await _cleanup_test_repo(test_db_session, repo.id)
        await test_db_session.execute(delete(User).where(User.id == user.id))
        await test_db_session.commit()


async def test_another_user_repo_returns_404(
    test_db_session: AsyncSession,
    integration_client: httpx.AsyncClient,
) -> None:
    """Verify that querying another user's repository enforces ownership and returns 404."""
    user1 = _make_mock_user("owner-user", 990031)
    user2 = _make_mock_user("other-user", 990032)
    test_db_session.add_all([user1, user2])
    await test_db_session.flush()

    # Repo owned by User 1
    repo1 = _make_mock_repo(user1.id, "owner-user/private-work", 880031)
    test_db_session.add(repo1)
    await test_db_session.commit()

    try:
        # Create session cookies for both users
        user1_token = create_session_token({"sub": str(user1.id), "login": user1.login})
        user2_token = create_session_token({"sub": str(user2.id), "login": user2.login})


        cookies_user1 = {settings.SESSION_COOKIE_NAME: user1_token}
        cookies_user2 = {settings.SESSION_COOKIE_NAME: user2_token}

        # 1. User 1 accesses their own repo -> 200 OK
        resp_owner = await integration_client.get(f"/repos/{repo1.id}", cookies=cookies_user1)
        assert resp_owner.status_code == 200
        assert resp_owner.json()["full_name"] == "owner-user/private-work"

        # 2. User 2 accesses User 1's repo -> 404 NOT FOUND (ownership enforced)
        resp_unauthorized = await integration_client.get(f"/repos/{repo1.id}", cookies=cookies_user2)
        assert resp_unauthorized.status_code == 404
        assert "Repository not found" in resp_unauthorized.json()["detail"]

    finally:
        await _cleanup_test_repo(test_db_session, repo1.id)
        await test_db_session.execute(delete(User).where(User.id.in_([user1.id, user2.id])))
        await test_db_session.commit()
