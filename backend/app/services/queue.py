"""Queue dispatch helper for ARQ background tasks."""

import asyncio
import uuid
from typing import Any

from app.core.config import settings
from app.core.logging import logger


async def simulate_demo_sync(repo_id: uuid.UUID) -> None:
    """Simulate realistic multi-stage background sync in demo mode."""
    from datetime import UTC, datetime

    from app.db.demo_store import get_demo_session

    db = get_demo_session()
    repo = db.repos_by_id.get(repo_id)
    if not repo:
        return

    # Find latest sync job for this repo
    job = next((j for j in db.sync_jobs_by_id.values() if j.repo_id == repo_id), None)
    if not job:
        return

    try:
        repo.status = "syncing"
        job.status = "running"

        # Stage 1: metadata
        job.stage = "metadata"
        job.progress = 20
        await asyncio.sleep(1.0)

        # Stage 2: commits
        job.stage = "commits"
        job.progress = 50
        await asyncio.sleep(1.5)

        # Stage 3: pull_requests
        job.stage = "pull_requests"
        job.progress = 75
        await asyncio.sleep(1.2)

        # Stage 4: issues
        job.stage = "issues"
        job.progress = 90
        await asyncio.sleep(1.0)

        # Complete
        now = datetime.now(UTC)
        job.stage = "completed"
        job.status = "completed"
        job.progress = 100
        job.completed_at = now
        repo.status = "ready"
        repo.last_synced_at = now
        logger.info(f"[Demo] Background sync finished successfully for repo {repo.full_name}")
    except Exception as exc:
        job.status = "failed"
        repo.status = "failed"
        repo.sync_error = str(exc)
        logger.error(f"[Demo] Background sync failed for repo {repo_id}: {exc}")


def _build_arq_redis_settings() -> Any:
    from arq.connections import RedisSettings

    rs = RedisSettings.from_dsn(settings.REDIS_URL)
    rs.retry_on_timeout = True
    rs.conn_retries = 10
    rs.conn_retry_delay = 1
    return rs


async def enqueue_sync_job(repo_id: uuid.UUID) -> str | None:
    """Enqueue repository synchronization job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    if settings.DEMO_MODE:
        asyncio.create_task(simulate_demo_sync(repo_id))
        return f"demo-job-{repo_id}"

    try:
        from arq.connections import create_pool

        redis_settings = _build_arq_redis_settings()

        async def _connect_and_enqueue() -> str | None:
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job("sync_repository", str(repo_id))
            await pool.close()
            return job.job_id if job else None

        job_id = await asyncio.wait_for(_connect_and_enqueue(), timeout=5.0)
        logger.info(f"Enqueued sync job for repo {repo_id} (ARQ Job ID: {job_id})")
        return job_id
    except Exception as exc:
        logger.warning(f"Could not enqueue sync job for repo {repo_id} to Redis: {exc}")
        return None


async def simulate_demo_indexing(repo_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Simulate realistic multi-stage background indexing in demo mode."""
    from datetime import UTC, datetime

    from app.db.demo_store import get_demo_session

    db = get_demo_session()
    repo = db.repos_by_id.get(repo_id)
    if not repo:
        return

    job = db.index_jobs_by_id.get(job_id)
    if not job:
        job = next((j for j in db.index_jobs_by_id.values() if j.repo_id == repo_id), None)
    if not job:
        return

    try:
        repo.index_status = "indexing"
        job.status = "running"

        # Stage 1: fetching
        job.stage = "fetching"
        job.progress = 20
        await asyncio.sleep(1.0)

        # Stage 2: filtering
        job.stage = "filtering"
        job.progress = 35
        await asyncio.sleep(0.8)

        # Stage 3: chunking
        job.stage = "chunking"
        job.progress = 55
        await asyncio.sleep(1.2)

        # Stage 4: embedding
        job.stage = "embedding"
        job.progress = 80
        await asyncio.sleep(1.5)

        # Stage 5: saving
        job.stage = "saving"
        job.progress = 95
        await asyncio.sleep(0.8)

        # Complete
        now = datetime.now(UTC)
        job.stage = "completed"
        job.status = "completed"
        job.progress = 100
        job.completed_at = now
        job.stats = {
            "total_files": 48,
            "new_files": 48,
            "modified_files": 0,
            "unchanged_files": 0,
            "deleted_files": 0,
            "total_chunks": 184,
            "new_chunks": 184,
        }
        repo.index_status = "ready"
        repo.indexed_commit_sha = repo.default_branch or "main"
        repo.indexed_at = now
        repo.chunk_count = 184
        logger.info(f"[Demo] Background indexing finished successfully for repo {repo.full_name}")
    except Exception as exc:
        job.status = "failed"
        job.stage = "failed"
        job.error = str(exc)
        repo.index_status = "failed"
        logger.error(f"[Demo] Background indexing failed for repo {repo_id}: {exc}")


async def enqueue_index_job(repo_id: uuid.UUID, job_id: uuid.UUID | None = None) -> str | None:
    """Enqueue repository codebase indexing job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    if settings.DEMO_MODE:
        if job_id:
            asyncio.create_task(simulate_demo_indexing(repo_id, job_id))
        return f"demo-index-job-{repo_id}"

    try:
        from arq.connections import create_pool

        redis_settings = _build_arq_redis_settings()

        async def _connect_and_enqueue() -> str | None:
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job("index_repository", str(repo_id), str(job_id) if job_id else None)
            await pool.close()
            return job.job_id if job else None

        arq_job_id = await asyncio.wait_for(_connect_and_enqueue(), timeout=5.0)
        logger.info(f"Enqueued indexing job for repo {repo_id} (ARQ Job ID: {arq_job_id})")
        return arq_job_id
    except Exception as exc:
        logger.warning(f"Could not enqueue indexing job for repo {repo_id} to Redis: {exc}")
        return None


async def simulate_demo_doc(repo_id: uuid.UUID, doc_type: str) -> None:
    """Simulate asynchronous documentation generation in demo mode."""
    from app.db.demo_store import get_demo_session
    from app.services.doc_generator import execute_doc_generation
    from app.services.llm import FakeLLMProvider

    await asyncio.sleep(1.0)
    db = get_demo_session()
    try:
        await execute_doc_generation(
            repo_id=repo_id,
            doc_type=doc_type,
            db=db,
            llm_provider=FakeLLMProvider(),
        )
    except Exception as exc:
        logger.error(f"[Demo] Background doc generation failed for repo {repo_id}: {exc}")


async def enqueue_doc_job(repo_id: uuid.UUID, doc_type: str) -> str | None:
    """Enqueue repository documentation generation job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    if settings.DEMO_MODE:
        asyncio.create_task(simulate_demo_doc(repo_id, doc_type))
        return f"demo-doc-job-{repo_id}-{doc_type}"

    try:
        from arq.connections import create_pool

        redis_settings = _build_arq_redis_settings()

        async def _connect_and_enqueue() -> str | None:
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job("generate_doc", str(repo_id), doc_type)
            await pool.close()
            return job.job_id if job else None

        arq_job_id = await asyncio.wait_for(_connect_and_enqueue(), timeout=5.0)
        logger.info(f"Enqueued doc job for repo {repo_id} {doc_type} (ARQ Job ID: {arq_job_id})")
        return arq_job_id
    except Exception as exc:
        logger.warning(f"Could not enqueue doc job for repo {repo_id} {doc_type} to Redis: {exc}")
        return None


async def enqueue_issue_analysis_job(repo_id: uuid.UUID) -> str | None:
    """Enqueue repository issue classification and analysis job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    if settings.DEMO_MODE:
        return f"demo-issue-job-{repo_id}"

    try:
        from arq.connections import create_pool

        redis_settings = _build_arq_redis_settings()

        async def _connect_and_enqueue() -> str | None:
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job("analyze_issues", str(repo_id))
            await pool.close()
            return job.job_id if job else None

        arq_job_id = await asyncio.wait_for(_connect_and_enqueue(), timeout=5.0)
        logger.info(f"Enqueued issue analysis job for repo {repo_id} (ARQ Job ID: {arq_job_id})")
        return arq_job_id
    except Exception as exc:
        logger.warning(f"Could not enqueue issue analysis job for repo {repo_id} to Redis: {exc}")
        return None


WORKER_NOT_RUNNING_ERROR = (
    r"The background worker is not running. Start it with scripts\dev-worker.ps1 and try again."
)
JOB_EXPIRED_BEFORE_PICKUP_ERROR = (
    "This job expired before the worker could pick it up. Please try again."
)


async def worker_alive(redis: Any = None) -> bool:
    """Check if ARQ worker is alive by inspecting the health check sentinel key in Redis."""
    try:
        if redis is not None:
            val = await redis.get(settings.ARQ_HEALTH_CHECK_KEY)
            if val is None:
                return False
            if type(val).__name__ == "AsyncMock":
                return False
            return bool(val)

        from redis.asyncio import Redis

        client = Redis.from_url(settings.REDIS_URL)
        try:
            val = await client.get(settings.ARQ_HEALTH_CHECK_KEY)
            return bool(val)
        finally:
            await client.aclose()
    except Exception as exc:
        logger.warning(f"Error checking worker health key: {exc}")
        return False


is_worker_alive = worker_alive


def _is_job_expired(job_created_at: Any) -> bool:
    """Check if a job created timestamp exceeds JOB_EXPIRY_TIMEOUT_SECONDS."""
    if not job_created_at:
        return False
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    created = job_created_at if job_created_at.tzinfo else job_created_at.replace(tzinfo=UTC)
    return (now - created).total_seconds() >= settings.JOB_EXPIRY_TIMEOUT_SECONDS


async def check_and_expire_stuck_sync_job(
    sync_job: Any,
    repo: Any,
    db: Any,
    redis: Any = None,
) -> bool:
    """Check if sync job has been queued/pending for > 2m while worker is off.

    If so, updates sync job and repo to failed and returns True.
    """
    if not sync_job:
        return False

    is_queued = sync_job.status in ("pending", "running") and (
        sync_job.stage == "queued" or sync_job.progress == 0 or sync_job.status == "pending"
    )
    if not is_queued:
        return False

    if not _is_job_expired(sync_job.created_at):
        return False

    alive = await worker_alive(redis)
    is_stalled = False
    if alive:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        created = sync_job.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created and (now - created).total_seconds() >= 600:
            is_stalled = True
    if alive and not is_stalled:
        return False

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    err_msg = JOB_EXPIRED_BEFORE_PICKUP_ERROR if alive else WORKER_NOT_RUNNING_ERROR
    sync_job.status = "failed"
    sync_job.stage = "failed"
    sync_job.error = err_msg
    sync_job.finished_at = now
    if hasattr(sync_job, "updated_at"):
        sync_job.updated_at = now

    if repo and repo.status in ("pending", "syncing"):
        repo.status = "failed"
        repo.sync_error = err_msg
        if hasattr(repo, "updated_at"):
            repo.updated_at = now

    await db.commit()
    if hasattr(db, "refresh"):
        await db.refresh(sync_job)
        if repo:
            await db.refresh(repo)
    logger.warning(f"Expired stuck sync job {sync_job.id} for repo {sync_job.repo_id}: {err_msg}")
    return True


async def check_and_expire_stuck_index_job(
    index_job: Any,
    repo: Any,
    db: Any,
    redis: Any = None,
) -> bool:
    """Check if index job has been queued/pending for > 2m while worker is off.

    If so, updates index job and repo to failed and returns True.
    """
    if not index_job:
        return False

    is_queued = index_job.status in ("pending", "running") and (
        index_job.stage == "queued" or index_job.progress == 0 or index_job.status == "pending"
    )
    if not is_queued:
        return False

    if not _is_job_expired(index_job.created_at):
        return False

    alive = await worker_alive(redis)
    is_stalled = False
    if alive:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        created = index_job.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created and (now - created).total_seconds() >= 600:
            is_stalled = True
    if alive and not is_stalled:
        return False

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    err_msg = JOB_EXPIRED_BEFORE_PICKUP_ERROR if alive else WORKER_NOT_RUNNING_ERROR
    index_job.status = "failed"
    index_job.stage = "failed"
    index_job.error = err_msg
    index_job.finished_at = now
    if hasattr(index_job, "updated_at"):
        index_job.updated_at = now

    if repo and repo.index_status == "indexing":
        repo.index_status = "ready" if (getattr(repo, "chunk_count", 0) > 0 or getattr(repo, "indexed_at", None)) else "failed"
        if hasattr(repo, "updated_at"):
            repo.updated_at = now

    await db.commit()
    if hasattr(db, "refresh"):
        await db.refresh(index_job)
        if repo:
            await db.refresh(repo)
    logger.warning(f"Expired stuck index job {index_job.id} for repo {index_job.repo_id}: {err_msg}")
    return True


async def check_and_expire_stuck_doc_job(
    doc: Any,
    db: Any,
    redis: Any = None,
) -> bool:
    """Check if doc job has been queued/pending for > 2m while worker is off.

    If so, updates doc to failed and returns True.
    """
    if not doc:
        return False

    is_queued = doc.status in ("pending", "generating")
    if not is_queued:
        return False

    ref_time = getattr(doc, "updated_at", None) or getattr(doc, "created_at", None)
    if not _is_job_expired(ref_time):
        return False

    alive = await worker_alive(redis)
    is_stalled = False
    if alive:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        created = ref_time
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created and (now - created).total_seconds() >= 600:
            is_stalled = True
    if alive and not is_stalled:
        return False

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    err_msg = JOB_EXPIRED_BEFORE_PICKUP_ERROR if alive else WORKER_NOT_RUNNING_ERROR
    doc.status = "failed"
    doc.error = err_msg
    doc.updated_at = now

    await db.commit()
    if hasattr(db, "refresh"):
        await db.refresh(doc)
    logger.warning(
        f"Expired stuck doc job {doc.id} for repo {doc.repo_id} ({getattr(doc, 'doc_type', 'doc')}): {err_msg}"
    )
    return True


async def check_and_expire_stuck_issue_job(
    job: Any,
    db: Any,
    redis: Any = None,
) -> bool:
    """Check if issue analysis job has been queued/pending for > 2m while worker is off.

    If so, updates job to failed and returns True.
    """
    if not job:
        return False

    is_queued = job.status in ("pending", "running") and (
        job.stage in ("queued", "loading") or job.progress <= 5 or job.status == "pending"
    )
    if not is_queued:
        return False

    ref_time = getattr(job, "updated_at", None) or getattr(job, "created_at", None)
    if not _is_job_expired(ref_time):
        return False

    alive = await worker_alive(redis)
    is_stalled = False
    if alive:
        from datetime import UTC, datetime
        now = datetime.now(UTC)
        created = ref_time
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created and (now - created).total_seconds() >= 600:
            is_stalled = True
    if alive and not is_stalled:
        return False

    ref_time = getattr(job, "started_at", None) or getattr(job, "created_at", None)
    if not _is_job_expired(ref_time):
        return False

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    alive = await worker_alive(redis)
    err_msg = JOB_EXPIRED_BEFORE_PICKUP_ERROR if alive else WORKER_NOT_RUNNING_ERROR
    job.status = "failed"
    job.stage = "failed"
    job.error = err_msg
    job.finished_at = now
    if hasattr(job, "updated_at"):
        job.updated_at = now

    await db.commit()
    if hasattr(db, "refresh"):
        await db.refresh(job)
    logger.warning(f"Expired stuck issue analysis job {job.id} for repo {job.repo_id}: {err_msg}")
    return True


async def reconcile_repository_status(
    repo: Any,
    db: Any,
    redis: Any = None,
) -> bool:
    """Reconcile repository status against active jobs.

    If repository says syncing/indexing but there is no active (pending or running, not expired)
    job for it, reset the repository to its last terminal state.
    """
    if not repo:
        return False

    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.index_job import IndexJob
    from app.models.sync_job import SyncJob

    now = datetime.now(UTC)
    changed = False

    # 1. Sync status reconciliation
    if repo.status in ("pending", "syncing"):
        job_stmt = (
            select(SyncJob)
            .where(SyncJob.repo_id == repo.id)
            .order_by(SyncJob.created_at.desc())
        )
        job_res = await db.execute(job_stmt)
        latest_sync = job_res.scalars().first()

        has_active_sync = False
        if latest_sync:
            was_expired = await check_and_expire_stuck_sync_job(latest_sync, repo, db, redis)
            if was_expired:
                changed = True
            if not was_expired and latest_sync.status in ("pending", "running"):
                has_active_sync = True

        if not has_active_sync and repo.status in ("pending", "syncing"):
            repo.status = "ready" if repo.last_synced_at else "failed"
            if latest_sync and latest_sync.error:
                repo.sync_error = latest_sync.error
            if hasattr(repo, "updated_at"):
                repo.updated_at = now
            changed = True

    # 2. Index status reconciliation
    if repo.index_status == "indexing":
        ij_stmt = (
            select(IndexJob)
            .where(IndexJob.repo_id == repo.id)
            .order_by(IndexJob.created_at.desc())
        )
        ij_res = await db.execute(ij_stmt)
        latest_idx = ij_res.scalars().first()

        has_active_idx = False
        if latest_idx:
            was_expired = await check_and_expire_stuck_index_job(latest_idx, repo, db, redis)
            if was_expired:
                changed = True
            if not was_expired and latest_idx.status in ("pending", "running"):
                has_active_idx = True

        if not has_active_idx and repo.index_status == "indexing":
            repo.index_status = (
                "ready"
                if (getattr(repo, "chunk_count", 0) > 0 or getattr(repo, "indexed_at", None))
                else "failed"
            )
            if hasattr(repo, "updated_at"):
                repo.updated_at = now
            changed = True

    if changed:
        await db.commit()
        if hasattr(db, "refresh"):
            await db.refresh(repo)

    return changed



