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


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook: initializes async database engine and session maker."""
    setup_logging()
    logger.info("ARQ Worker starting up; initializing database session factory...")
    from app.db.session import async_session_maker, engine, verify_db_connection

    # Ensure DB connection with backoff retry for Neon cold starts
    await verify_db_connection()

    ctx["engine"] = engine
    ctx["session_factory"] = async_session_maker
    logger.info("ARQ Worker initialization complete.")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook: gracefully disposes database engine connections."""
    logger.info("ARQ Worker shutting down; disposing database engine...")
    engine = ctx.get("engine")
    if engine:
        await engine.dispose()
    logger.info("ARQ Worker shutdown complete.")


class WorkerSettings:
    """ARQ Worker process settings."""

    functions = [sync_repository, index_repository, generate_doc]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    poll_delay = settings.ARQ_POLL_DELAY
    max_jobs = 10
    job_timeout = 1800  # 30 minutes max per indexing / sync run
