"""Pytest test fixtures and FastAPI test client setup."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.db.session import get_db, get_redis
from app.main import app
from app.models.user import User


class FakeScalarResult:
    """Mock for SQLAlchemy ScalarResult."""
    def __init__(self, item: Any):
        self._item = item

    def scalar_one_or_none(self) -> Any:
        return self._item

    def scalar(self) -> Any:
        return self._item


class InMemoryAsyncSession:
    """Lightweight in-memory AsyncSession for isolated route and integration tests."""

    def __init__(self) -> None:
        self.users_by_id: dict[uuid.UUID, User] = {}
        self.users_by_github_id: dict[int, User] = {}
        self.added: list[Any] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeScalarResult:
        stmt_str = str(statement)
        # Check health check query: SELECT 1
        if "1" in stmt_str and "SELECT" in stmt_str and "users" not in stmt_str:
            return FakeScalarResult(1)

        # Check queries on User model
        where_part = stmt_str.split("WHERE", 1)[1] if "WHERE" in stmt_str else stmt_str

        if "users.github_id" in where_part:
            # Extract github_id from compiled params or bound parameters
            github_id = None
            if hasattr(statement, "compile"):
                compiled = statement.compile()
                for v in compiled.params.values():
                    if isinstance(v, int):
                        github_id = v
                        break
            user = self.users_by_github_id.get(github_id) if github_id else None
            return FakeScalarResult(user)

        if "users.id" in where_part:
            user_id = None
            if hasattr(statement, "compile"):
                compiled = statement.compile()
                for v in compiled.params.values():
                    if isinstance(v, uuid.UUID):
                        user_id = v
                        break
                    elif isinstance(v, str):
                        try:
                            user_id = uuid.UUID(v)
                            break
                        except ValueError:
                            pass
            user = self.users_by_id.get(user_id) if user_id else None
            return FakeScalarResult(user)

        return FakeScalarResult(None)

    def add(self, instance: Any) -> None:
        if isinstance(instance, User):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = datetime.now(UTC)
            if not instance.updated_at:
                instance.updated_at = datetime.now(UTC)
            self.users_by_id[instance.id] = instance
            self.users_by_github_id[instance.github_id] = instance
        self.added.append(instance)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.fixture
def fake_db() -> InMemoryAsyncSession:
    """Fixture providing clean in-memory database storage."""
    return InMemoryAsyncSession()


@pytest.fixture
def fake_redis() -> AsyncMock:
    """Fixture providing mock Redis client."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock


@pytest_asyncio.fixture
async def client(fake_db: InMemoryAsyncSession, fake_redis: AsyncMock) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Asynchronous HTTP test client with overridden dependencies."""
    async def override_get_db():
        yield fake_db

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client

    app.dependency_overrides.clear()
