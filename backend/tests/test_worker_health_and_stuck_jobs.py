"""Unit tests for worker health check, worker_alive, and stuck jobs expiration."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.models.index_job import IndexJob
from app.models.repo_doc import RepoDoc
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.services.queue import (
    WORKER_NOT_RUNNING_ERROR,
    check_and_expire_stuck_doc_job,
    check_and_expire_stuck_index_job,
    check_and_expire_stuck_sync_job,
    worker_alive,
)
from tests.conftest import InMemoryAsyncSession


@pytest.mark.asyncio
async def test_worker_alive_true_false() -> None:
    """Validate worker_alive correctly reports True/False based on Redis health key."""
    # 1. When Redis returns health check data -> worker is alive
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"May-01 12:00:00 j_complete=5 j_failed=0"
    alive = await worker_alive(mock_redis)
    assert alive is True

    # 2. When Redis key does not exist (None) -> worker is not running
    mock_redis.get.return_value = None
    alive = await worker_alive(mock_redis)
    assert alive is False

    # 3. When Redis raises an error -> safely fails to False
    mock_redis.get.side_effect = ConnectionError("Redis unreachable")
    alive = await worker_alive(mock_redis)
    assert alive is False


@pytest.mark.asyncio
async def test_sync_job_queued_over_2_minutes_worker_not_alive_marked_failed(
    fake_db: InMemoryAsyncSession,
) -> None:
    """A sync job queued for over 2 minutes while worker is off must be marked failed with exact error message."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        github_id=12345,
        full_name="test-owner/test-repo",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    old_created_at = datetime.now(UTC) - timedelta(minutes=2, seconds=5)
    sync_job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        created_at=old_created_at,
    )
    fake_db.add(sync_job)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Worker is NOT alive

    expired = await check_and_expire_stuck_sync_job(sync_job, repo, fake_db, mock_redis)
    assert expired is True
    assert sync_job.status == "failed"
    assert sync_job.stage == "failed"
    assert sync_job.error == WORKER_NOT_RUNNING_ERROR
    assert "scripts\\dev-worker.ps1" in sync_job.error
    assert repo.status == "failed"
    assert repo.sync_error == WORKER_NOT_RUNNING_ERROR


@pytest.mark.asyncio
async def test_sync_job_queued_over_2_minutes_worker_alive_left_alone(
    fake_db: InMemoryAsyncSession,
) -> None:
    """A sync job queued for over 2 minutes while the worker IS alive must be left alone."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        github_id=12345,
        full_name="test-owner/test-repo",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    old_created_at = datetime.now(UTC) - timedelta(minutes=3)
    sync_job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        created_at=old_created_at,
    )
    fake_db.add(sync_job)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"active_worker_sentinel"  # Worker IS alive

    expired = await check_and_expire_stuck_sync_job(sync_job, repo, fake_db, mock_redis)
    assert expired is False
    assert sync_job.status == "pending"
    assert sync_job.stage == "queued"
    assert sync_job.error is None
    assert repo.status == "pending"


@pytest.mark.asyncio
async def test_sync_job_queued_under_2_minutes_worker_not_alive_left_alone(
    fake_db: InMemoryAsyncSession,
) -> None:
    """A sync job queued for less than 2 minutes is not expired, even if worker is not yet alive."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        github_id=12345,
        full_name="test-owner/test-repo",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    fresh_created_at = datetime.now(UTC) - timedelta(seconds=30)
    sync_job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        created_at=fresh_created_at,
    )
    fake_db.add(sync_job)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Worker is not alive

    expired = await check_and_expire_stuck_sync_job(sync_job, repo, fake_db, mock_redis)
    assert expired is False
    assert sync_job.status == "pending"


@pytest.mark.asyncio
async def test_index_job_queued_over_2_minutes_worker_not_alive_marked_failed(
    fake_db: InMemoryAsyncSession,
) -> None:
    """An index job queued for over 2 minutes with worker not alive must be marked failed."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        github_id=12345,
        full_name="test-owner/test-repo",
        default_branch="main",
        index_status="indexing",
    )
    fake_db.add(repo)

    old_created_at = datetime.now(UTC) - timedelta(minutes=2, seconds=10)
    index_job = IndexJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="running",
        stage="queued",
        progress=0,
        created_at=old_created_at,
    )
    fake_db.add(index_job)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    expired = await check_and_expire_stuck_index_job(index_job, repo, fake_db, mock_redis)
    assert expired is True
    assert index_job.status == "failed"
    assert index_job.stage == "failed"
    assert index_job.error == WORKER_NOT_RUNNING_ERROR
    assert repo.index_status == "failed"


@pytest.mark.asyncio
async def test_api_get_sync_status_expires_stuck_job(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    fake_redis: AsyncMock,
) -> None:
    """GET /repos/{id}/sync-status on stuck job returns failed with helpful worker message."""
    from app.core.security import create_session_token, encrypt_token

    user = User(
        id=uuid.uuid4(),
        github_id=892301,
        login="testuser",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=89230101,
        full_name="testuser/repo1",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    stuck_time = datetime.now(UTC) - timedelta(minutes=3)
    sync_job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        created_at=stuck_time,
    )
    fake_db.add(sync_job)

    # Worker is off
    fake_redis.get.return_value = None

    response = await client.get(
        f"/repos/{repo.id}/sync-status",
        cookies=cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["stage"] == "failed"
    assert "The background worker is not running" in data["error"]


@pytest.mark.asyncio
async def test_api_trigger_sync_clears_expired_stuck_job_instead_of_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    fake_redis: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /repos/{id}/sync when previous job is expired stuck does NOT return 409 forever."""
    from unittest.mock import AsyncMock as AM

    from app.core.security import create_session_token, encrypt_token

    monkeypatch.setattr("app.api.routes.repos.enqueue_sync_job", AM(return_value="arq-job-new"))

    user = User(
        id=uuid.uuid4(),
        github_id=892301,
        login="testuser",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=89230101,
        full_name="testuser/repo1",
        default_branch="main",
        status="pending",
    )
    fake_db.add(repo)

    stuck_time = datetime.now(UTC) - timedelta(minutes=5)
    old_sync_job = SyncJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        created_at=stuck_time,
    )
    fake_db.add(old_sync_job)

    # Worker is off
    fake_redis.get.return_value = None

    # Triggering sync should succeed (202) instead of 409 Conflict!
    response = await client.post(
        f"/repos/{repo.id}/sync",
        cookies=cookies,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    # Old job should have been marked failed
    assert old_sync_job.status == "failed"


@pytest.mark.asyncio
async def test_api_trigger_index_clears_expired_stuck_job_instead_of_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    fake_redis: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /repos/{id}/index when previous job is expired stuck does NOT return 409 forever."""
    from unittest.mock import AsyncMock as AM

    from app.core.security import create_session_token, encrypt_token

    monkeypatch.setattr("app.api.routes.repos.enqueue_index_job", AM(return_value="arq-job-index-new"))

    user = User(
        id=uuid.uuid4(),
        github_id=892301,
        login="testuser",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=89230101,
        full_name="testuser/repo1",
        default_branch="main",
        index_status="indexing",
    )
    fake_db.add(repo)

    stuck_time = datetime.now(UTC) - timedelta(minutes=5)
    old_index_job = IndexJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="running",
        stage="queued",
        progress=0,
        created_at=stuck_time,
    )
    fake_db.add(old_index_job)

    # Worker is off
    fake_redis.get.return_value = None

    # Triggering index should succeed (202) instead of 409 Conflict!
    response = await client.post(
        f"/repos/{repo.id}/index",
        cookies=cookies,
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "running"
    # Old job should have been marked failed
    assert old_index_job.status == "failed"


@pytest.mark.asyncio
async def test_doc_job_queued_over_2_minutes_worker_not_alive_marked_failed(
    fake_db: InMemoryAsyncSession,
) -> None:
    """A doc job pending for over 2 minutes while worker is off must be marked failed with exact error message."""
    stuck_time = datetime.now(UTC) - timedelta(minutes=2, seconds=10)
    doc = RepoDoc(
        id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        doc_type="architecture",
        status="pending",
        citations=[],
        created_at=stuck_time,
        updated_at=stuck_time,
    )
    fake_db.add(doc)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    expired = await check_and_expire_stuck_doc_job(
        doc,
        fake_db,
        redis=mock_redis,
    )
    assert expired is True
    assert doc.status == "failed"
    assert doc.error == WORKER_NOT_RUNNING_ERROR


@pytest.mark.asyncio
async def test_api_trigger_doc_clears_expired_stuck_job_instead_of_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    fake_redis: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /repos/{id}/docs/{type} when previous doc job is stuck does NOT return 409 forever."""
    from unittest.mock import AsyncMock as AM

    from app.core.security import create_session_token, encrypt_token

    monkeypatch.setattr("app.api.routes.repos.enqueue_doc_job", AM(return_value="arq-job-doc-new"))

    user = User(
        id=uuid.uuid4(),
        github_id=892302,
        login="testuser2",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken2"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=89230202,
        full_name="testuser2/repo2",
        default_branch="main",
        index_status="ready",
    )
    fake_db.add(repo)

    stuck_time = datetime.now(UTC) - timedelta(minutes=5)
    old_doc = RepoDoc(
        id=uuid.uuid4(),
        repo_id=repo.id,
        doc_type="architecture",
        status="pending",
        citations=[],
        created_at=stuck_time,
        updated_at=stuck_time,
    )
    fake_db.add(old_doc)

    # Worker is off
    fake_redis.get.return_value = None

    response = await client.post(
        f"/repos/{repo.id}/docs/architecture/generate",
        cookies=cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_api_get_doc_expires_stuck_job(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    fake_redis: AsyncMock,
) -> None:
    """GET /repos/{id}/docs/{type} when doc job is stuck marks it failed."""
    from app.core.security import create_session_token, encrypt_token

    user = User(
        id=uuid.uuid4(),
        github_id=892303,
        login="testuser3",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken3"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=89230303,
        full_name="testuser3/repo3",
        default_branch="main",
        index_status="ready",
    )
    fake_db.add(repo)

    stuck_time = datetime.now(UTC) - timedelta(minutes=5)
    stuck_doc = RepoDoc(
        id=uuid.uuid4(),
        repo_id=repo.id,
        doc_type="readme",
        status="pending",
        citations=[],
        created_at=stuck_time,
        updated_at=stuck_time,
    )
    fake_db.add(stuck_doc)

    # Worker is off
    fake_redis.get.return_value = None

    response = await client.get(
        f"/repos/{repo.id}/docs/readme",
        cookies=cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == WORKER_NOT_RUNNING_ERROR



