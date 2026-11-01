import sys
from typing import Any

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.services.queue import is_worker_alive, worker_alive

__all__ = ["WorkerSettings", "is_worker_alive", "worker_alive"]



async def sync_repository(ctx: dict[str, Any], repo_id: str) -> None:
    """Entrypoint function for ARQ background sync tasks."""
    from app.services.sync_service import execute_repo_sync

    logger.info(f"Worker received sync_repository job for repo {repo_id}")
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with session_factory() as db:
        await execute_repo_sync(repo_id=repo_id, db=db)


async def index_repository(ctx: dict[str, Any], repo_id: str, job_id: str | None = None) -> None:
    """Entrypoint function for ARQ background codebase indexing tasks."""
    from app.services.indexer import execute_repo_indexing

    logger.info(f"Worker received index_repository job for repo {repo_id} (job_id: {job_id})")
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with session_factory() as db:
        await execute_repo_indexing(repo_id=repo_id, db=db, job_id=job_id)


async def generate_doc(ctx: dict[str, Any], repo_id: str, doc_type: str) -> None:
    """Entrypoint function for ARQ background documentation generation tasks."""
    import uuid

    from app.services.doc_generator import execute_doc_generation

    logger.info(f"Worker received generate_doc job for repo {repo_id} (doc_type: {doc_type})")
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with session_factory() as db:
        await execute_doc_generation(repo_id=uuid.UUID(repo_id), doc_type=doc_type, db=db)


async def analyze_issues(ctx: dict[str, Any], repo_id: str) -> None:
    """Entrypoint function for ARQ background issue classification and embedding tasks."""
    import uuid

    from app.services.issue_analysis import execute_issue_analysis

    logger.info(f"Worker received analyze_issues job for repo {repo_id}")
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with session_factory() as db:
        await execute_issue_analysis(repo_id=uuid.UUID(repo_id), db=db)


async def _reconcile_interrupted_jobs_on_startup(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Mark all running jobs as failed due to worker restart and reconcile repo statuses."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.analysis_job import AnalysisJob
    from app.models.index_job import IndexJob
    from app.models.repo_doc import RepoDoc
    from app.models.repository import Repository
    from app.models.sync_job import SyncJob
    from app.services.queue import reconcile_repository_status

    now = datetime.now(UTC)
    INTERRUPTED_MSG = "Interrupted by a worker restart"

    try:
        async with session_factory() as db:
            repo_ids: set[Any] = set()

            # 1. Sync jobs
            res = await db.execute(select(SyncJob).where(SyncJob.status == "running"))
            running_syncs = res.scalars().all()
            for j in running_syncs:
                j.status = "failed"
                j.stage = "failed"
                j.error = INTERRUPTED_MSG
                j.finished_at = now
                if hasattr(j, "updated_at"):
                    j.updated_at = now
                repo_ids.add(j.repo_id)

            # 2. Index jobs
            res = await db.execute(select(IndexJob).where(IndexJob.status == "running"))
            running_indices = res.scalars().all()
            for j in running_indices:
                j.status = "failed"
                j.stage = "failed"
                j.error = INTERRUPTED_MSG
                j.finished_at = now
                if hasattr(j, "updated_at"):
                    j.updated_at = now
                repo_ids.add(j.repo_id)

            # 3. Analysis jobs
            res = await db.execute(select(AnalysisJob).where(AnalysisJob.status == "running"))
            running_analyses = res.scalars().all()
            for j in running_analyses:
                j.status = "failed"
                j.stage = "failed"
                j.error = INTERRUPTED_MSG
                j.finished_at = now
                if hasattr(j, "updated_at"):
                    j.updated_at = now
                repo_ids.add(j.repo_id)

            # 4. Doc jobs
            res = await db.execute(select(RepoDoc).where(RepoDoc.status.in_(["pending", "generating"])))
            running_docs = res.scalars().all()
            for d in running_docs:
                d.status = "failed"
                d.error = INTERRUPTED_MSG
                if hasattr(d, "updated_at"):
                    d.updated_at = now

            await db.commit()

            # Reconcile affected repositories
            for rid in repo_ids:
                repo = await db.get(Repository, rid)
                if repo:
                    await reconcile_repository_status(repo, db)

            if running_syncs or running_indices or running_analyses or running_docs:
                logger.info(
                    f"Worker startup: marked interrupted jobs as failed ("
                    f"{len(running_syncs)} sync, {len(running_indices)} index, "
                    f"{len(running_analyses)} analysis, {len(running_docs)} doc)"
                )
    except Exception as exc:
        logger.warning(f"Error reconciling interrupted jobs on worker startup: {exc}")


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook: initializes async database engine and session maker."""
    setup_logging()
    logger.info("ARQ Worker starting up; initializing database session factory...")
    from app.db.session import async_session_maker, engine, verify_db_connection

    # Ensure DB connection with backoff retry for Neon cold starts
    await verify_db_connection()

    ctx["engine"] = engine
    ctx["session_factory"] = async_session_maker

    # Reconcile interrupted jobs on worker restart
    await _reconcile_interrupted_jobs_on_startup(async_session_maker)

    logger.info("ARQ Worker initialization complete.")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook: gracefully disposes database engine connections."""
    logger.info("ARQ Worker shutting down; disposing database engine...")
    engine = ctx.get("engine")
    if engine:
        await engine.dispose()
    logger.info("ARQ Worker shutdown complete.")


def _build_worker_redis_settings() -> RedisSettings:
    rs = RedisSettings.from_dsn(settings.REDIS_URL)
    rs.retry_on_timeout = True
    rs.conn_retries = 10
    rs.conn_retry_delay = 1
    return rs


class WorkerSettings:
    """ARQ Worker process settings."""

    functions = [sync_repository, index_repository, generate_doc, analyze_issues]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _build_worker_redis_settings()
    poll_delay = settings.ARQ_POLL_DELAY
    max_jobs = 10
    job_timeout = 1800  # 30 minutes max per indexing / sync run
    health_check_key = settings.ARQ_HEALTH_CHECK_KEY
    health_check_interval = settings.ARQ_HEALTH_CHECK_INTERVAL

