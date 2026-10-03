"""ARQ background worker configuration and lifecycle handlers."""

from typing import Any

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger, setup_logging


async def sync_repository(ctx: dict[str, Any], repo_id: str) -> None:
    """Entrypoint function for ARQ background sync tasks."""
    from app.services.sync_service import execute_repo_sync

    logger.info(f"Worker received sync_repository job for repo {repo_id}")
    session_factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with session_factory() as db:
        await execute_repo_sync(repo_id=repo_id, db=db)


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook: initializes async database engine and session maker."""
    setup_logging()
    logger.info("ARQ Worker starting up; initializing database session factory...")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    ctx["engine"] = engine
    ctx["session_factory"] = session_factory
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

    functions = [sync_repository]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
    job_timeout = 600  # 10 minutes max per sync run
