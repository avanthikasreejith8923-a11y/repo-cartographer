"""Database engine, async session factory, and Redis connection pool."""

import asyncio
from collections.abc import AsyncGenerator

import sqlalchemy as sa
from pgvector.asyncpg import register_vector
from redis import asyncio as aioredis
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger

# Async PostgreSQL Engine & Redis
if not settings.DEMO_MODE:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args=settings.asyncpg_connect_args,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_connection, connection_record):
        """Register pgvector binary codec on asyncpg connection."""
        if hasattr(dbapi_connection, "run_async"):
            dbapi_connection.run_async(register_vector)

    async_session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    redis_pool = aioredis.ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    redis_client = aioredis.Redis(connection_pool=redis_pool)
else:
    engine = None
    async_session_maker = None
    redis_pool = None
    redis_client = None


async def verify_db_connection(max_retries: int = 5, initial_delay: float = 1.0) -> None:
    """Verify database connectivity with exponential backoff retry for Neon compute auto-suspend."""
    if settings.DEMO_MODE or engine is None:
        return

    delay = initial_delay
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Checking database connection (attempt {attempt}/{max_retries})...")
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
            logger.info("Database connection established successfully.")
            return
        except Exception as exc:
            last_err = exc
            logger.warning(
                f"Database connection attempt {attempt} failed ({type(exc).__name__}: {exc}). "
                f"Retrying in {delay:.1f}s (Neon compute may be resuming)..."
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 2.0

    raise RuntimeError(
        f"Failed to establish database connection after {max_retries} attempts: {last_err}"
    ) from last_err


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an async SQLAlchemy session with automatic transaction handling."""
    if settings.DEMO_MODE:
        from app.db.demo_store import get_demo_session

        yield get_demo_session()  # type: ignore[misc]
        return

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> aioredis.Redis:
    """Dependency yielding the shared async Redis client."""
    if settings.DEMO_MODE:
        from app.db.demo_store import _demo_redis_instance

        return _demo_redis_instance  # type: ignore[return-value]

    return redis_client
