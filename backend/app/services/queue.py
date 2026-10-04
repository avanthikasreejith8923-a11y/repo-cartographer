"""Queue dispatch helper for ARQ background tasks."""

import asyncio
import uuid

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


async def enqueue_sync_job(repo_id: uuid.UUID) -> str | None:
    """Enqueue repository synchronization job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    if settings.DEMO_MODE:
        asyncio.create_task(simulate_demo_sync(repo_id))
        return f"demo-job-{repo_id}"

    try:
        from arq.connections import RedisSettings, create_pool

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

        async def _connect_and_enqueue() -> str | None:
            pool = await create_pool(redis_settings)
            job = await pool.enqueue_job("sync_repository", str(repo_id))
            await pool.close()
            return job.job_id if job else None

        job_id = await asyncio.wait_for(_connect_and_enqueue(), timeout=1.0)
        logger.info(f"Enqueued sync job for repo {repo_id} (ARQ Job ID: {job_id})")
        return job_id
    except Exception as exc:
        logger.warning(f"Could not enqueue sync job for repo {repo_id} to Redis: {exc}")
        return None
