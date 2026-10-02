"""Unit and integration tests for health check endpoint."""

from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_check_healthy(client: httpx.AsyncClient) -> None:
    """Validate /health endpoint returns 200 and healthy status when dependencies are reachable."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_check_redis_failure(
    client: httpx.AsyncClient,
    fake_redis: AsyncMock,
) -> None:
    """Validate /health returns 503 and degraded status when Redis ping raises an error."""
    fake_redis.ping.side_effect = ConnectionError("Redis connection refused")

    response = await client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["redis"] == "disconnected"
