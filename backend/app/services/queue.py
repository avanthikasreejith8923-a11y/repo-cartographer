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
        from arq.connections import RedisSettings, create_pool

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

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
        from arq.connections import RedisSettings, create_pool

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

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

