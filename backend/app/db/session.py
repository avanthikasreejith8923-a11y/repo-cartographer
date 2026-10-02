"""Database engine, async session factory, and Redis connection pool."""

from collections.abc import AsyncGenerator

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Async PostgreSQL Engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async Session Factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Async Redis Client
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)
redis_client = aioredis.Redis(connection_pool=redis_pool)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an async SQLAlchemy session with automatic transaction handling."""
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
    return redis_client
