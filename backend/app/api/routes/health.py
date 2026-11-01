"""Health check endpoint validating PostgreSQL and Redis connections."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from redis import asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import get_db, get_redis
from app.services.queue import worker_alive

router = APIRouter()


@router.get("/health", summary="Service Health and Connectivity Check")
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Check connectivity to PostgreSQL and Redis.

    Returns HTTP 200 when all core dependencies are healthy, or HTTP 503 if any core service is unreachable.
    Reports ARQ worker status as 'alive' or 'not running' without failing the endpoint.
    """
    db_status = "disconnected"
    redis_status = "disconnected"
    is_healthy = True

    # 1. Check PostgreSQL
    try:
        res = await db.execute(text("SELECT 1"))
        if res.scalar() == 1:
            db_status = "connected"
    except Exception as exc:
        logger.error(f"Health check PostgreSQL error: {exc}")
        is_healthy = False

    # 2. Check Redis
    try:
        pong = await redis.ping()
        if pong:
            redis_status = "connected"
    except Exception as exc:
        logger.error(f"Health check Redis error: {exc}")
        is_healthy = False

    # 3. Check ARQ Background Worker (informational only; does not mark service unhealthy)
    worker_status = "not running"
    if redis_status == "connected":
        try:
            if await worker_alive(redis):
                worker_status = "alive"
        except Exception as exc:
            logger.error(f"Health check Worker error: {exc}")

    overall_status = "healthy" if is_healthy else "degraded"
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "database": db_status,
        "redis": redis_status,
        "worker": worker_status,
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": "v1.0",
    }

