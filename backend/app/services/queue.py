"""Queue dispatch helper for ARQ background tasks."""

import uuid

from app.core.config import settings
from app.core.logging import logger


async def enqueue_sync_job(repo_id: uuid.UUID) -> str | None:
    """Enqueue repository synchronization job to ARQ Redis queue.

    Returns the ARQ job ID if enqueued, or None if queue is unavailable.
    """
    try:
        from arq.connections import RedisSettings, create_pool

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
        pool = await create_pool(redis_settings)
        job = await pool.enqueue_job("sync_repository", str(repo_id))
        await pool.close()
        logger.info(f"Enqueued sync job for repo {repo_id} (ARQ Job ID: {job.job_id if job else 'unknown'})")
        return job.job_id if job else None
    except Exception as exc:
        logger.warning(f"Could not enqueue sync job for repo {repo_id} to Redis: {exc}")
        return None
