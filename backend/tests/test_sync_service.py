"""Unit and pipeline tests for background sync stages and error handling."""

import uuid

import pytest
import respx

from app.core.security import encrypt_token
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.services.sync_service import execute_repo_sync
from tests.conftest import InMemoryAsyncSession


@pytest.fixture
def sync_fixtures(fake_db: InMemoryAsyncSession) -> tuple[User, Repository, SyncJob]:
    """Helper creating user, repository, and queued sync job."""
    user = User(
        id=uuid.uuid4(),
        github_id=888111,
        login="synctester",
        encrypted_access_token=encrypt_token("ghp_synctoken12345"),
    )
    fake_db.add(user)

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=999222,
        full_name="synctester/sample-repo",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
    )
    fake_db.add(job)

    return user, repo, job


@pytest.mark.asyncio
async def test_sync_metadata_stage_success(
    fake_db: InMemoryAsyncSession,
    sync_fixtures: tuple[User, Repository, SyncJob],
):
    """Verify metadata stage fetches repo details and updates status to ready."""
    user, repo, job = sync_fixtures

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path=f"/repos/{repo.full_name}").respond(
            status_code=200,
            json={
                "id": repo.github_id,
                "name": "sample-repo",
                "full_name": repo.full_name,
                "description": "Updated repository description from GitHub",
                "default_branch": "main",
                "language": "Python",
                "private": False,
            },
        )
        respx_mock.get(path=f"/repos/{repo.full_name}/commits").respond(
            status_code=200,
            json=[],
        )

        await execute_repo_sync(repo_id=repo.id, db=fake_db)

        assert repo.status == "ready"
        assert repo.description == "Updated repository description from GitHub"
        assert repo.language == "Python"
        assert repo.last_synced_at is not None
        assert repo.sync_error is None

        assert job.status == "completed"
        assert job.progress == 100
        assert job.error is None
        assert job.finished_at is not None


@pytest.mark.asyncio
async def test_sync_metadata_stage_failure_marks_failed(
    fake_db: InMemoryAsyncSession,
    sync_fixtures: tuple[User, Repository, SyncJob],
):
    """Verify GitHub error sets repo and job status to failed with captured error message."""
    user, repo, job = sync_fixtures

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path=f"/repos/{repo.full_name}").respond(
            status_code=404,
            json={"message": "Not Found"},
        )

        await execute_repo_sync(repo_id=repo.id, db=fake_db)

        assert repo.status == "failed"
        assert "request failed with status 404" in repo.sync_error.lower()

        assert job.status == "failed"
        assert job.stage == "failed"
        assert job.error is not None
        assert job.finished_at is not None


@pytest.mark.asyncio
async def test_sync_commits_stage_ingestion_and_stats(
    fake_db: InMemoryAsyncSession,
    sync_fixtures: tuple[User, Repository, SyncJob],
):
    """Verify commits are ingested and stats fetched for recent commits."""
    user, repo, job = sync_fixtures

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        # Metadata route
        respx_mock.get(path=f"/repos/{repo.full_name}").respond(
            status_code=200,
            json={"id": repo.github_id, "name": "sample-repo", "full_name": repo.full_name},
        )
        # Commits list route
        respx_mock.get(path=f"/repos/{repo.full_name}/commits").respond(
            status_code=200,
            json=[
                {
                    "sha": "1111222233334444555566667777888899990000",
                    "commit": {
                        "message": "feat: initial feature commit",
                        "author": {"name": "Alice Dev", "date": "2026-10-01T10:00:00Z"},
                        "committer": {"date": "2026-10-01T10:00:00Z"},
                    },
                    "author": {"login": "alicedev"},
                }
            ],
        )
        # Commit stats route
        respx_mock.get(path=f"/repos/{repo.full_name}/commits/1111222233334444555566667777888899990000").respond(
            status_code=200,
            json={
                "sha": "1111222233334444555566667777888899990000",
                "stats": {"additions": 42, "deletions": 5, "total": 47},
                "files": [{}, {}],
            },
        )

        await execute_repo_sync(repo_id=repo.id, db=fake_db)

        commits = [c for c in fake_db.commits_by_id.values() if c.repo_id == repo.id]
        assert len(commits) == 1
        commit = commits[0]
        assert commit.sha == "1111222233334444555566667777888899990000"
        assert commit.author_login == "alicedev"
        assert commit.author_name == "Alice Dev"
        assert commit.message == "feat: initial feature commit"
        assert commit.additions == 42
        assert commit.deletions == 5
        assert commit.files_changed == 2


@pytest.mark.asyncio
async def test_sync_commits_stage_idempotency(
    fake_db: InMemoryAsyncSession,
    sync_fixtures: tuple[User, Repository, SyncJob],
):
    """Verify running commit sync twice is idempotent and does not create duplicate rows."""
    user, repo, job = sync_fixtures

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path=f"/repos/{repo.full_name}").respond(
            status_code=200,
            json={"id": repo.github_id, "name": "sample-repo", "full_name": repo.full_name},
        )
        respx_mock.get(path=f"/repos/{repo.full_name}/commits").respond(
            status_code=200,
            json=[
                {
                    "sha": "aabbccddeeff0011223344556677889900aabbcc",
                    "commit": {
                        "message": "fix: bugfix",
                        "author": {"name": "Bob Dev", "date": "2026-10-02T10:00:00Z"},
                        "committer": {"date": "2026-10-02T10:00:00Z"},
                    },
                    "author": {"login": "bobdev"},
                }
            ],
        )
        respx_mock.get(path=f"/repos/{repo.full_name}/commits/aabbccddeeff0011223344556677889900aabbcc").respond(
            status_code=200,
            json={
                "sha": "aabbccddeeff0011223344556677889900aabbcc",
                "stats": {"additions": 10, "deletions": 2, "total": 12},
                "files": [{}],
            },
        )

        # First sync run
        await execute_repo_sync(repo_id=repo.id, db=fake_db)
        count_first = len([c for c in fake_db.commits_by_id.values() if c.repo_id == repo.id])
        assert count_first == 1

        # Second sync run
        await execute_repo_sync(repo_id=repo.id, db=fake_db)
        count_second = len([c for c in fake_db.commits_by_id.values() if c.repo_id == repo.id])
        assert count_second == 1
