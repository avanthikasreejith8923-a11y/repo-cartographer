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
from app.models.commit import Commit
from app.models.issue import Issue
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User


class FakeScalars:
    """Mock for SQLAlchemy scalars collection."""

    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return self._items

    def first(self) -> Any:
        return self._items[0] if self._items else None


class FakeScalarResult:
    """Mock for SQLAlchemy ScalarResult."""

    def __init__(self, item: Any, items: list[Any] | None = None):
        self._item = item
        self._items = items if items is not None else ([item] if item is not None else [])

    def scalar_one_or_none(self) -> Any:
        return self._item

    def scalar(self) -> Any:
        return self._item

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._items)


class InMemoryAsyncSession:
    """Lightweight in-memory AsyncSession for isolated route and integration tests."""

    def __init__(self) -> None:
        self.users_by_id: dict[uuid.UUID, User] = {}
        self.users_by_github_id: dict[int, User] = {}
        self.repos_by_id: dict[uuid.UUID, Repository] = {}
        self.sync_jobs_by_id: dict[uuid.UUID, SyncJob] = {}
        self.commits_by_id: dict[uuid.UUID, Commit] = {}
        self.pulls_by_id: dict[uuid.UUID, PullRequest] = {}
        self.issues_by_id: dict[uuid.UUID, Issue] = {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeScalarResult:
        stmt_str = str(statement)

        # Health check query: SELECT 1
        if "1" in stmt_str and "SELECT" in stmt_str and "users" not in stmt_str and "repositories" not in stmt_str:
            return FakeScalarResult(1)

        # Extract compiled bound params
        params: dict[str, Any] = {}
        if hasattr(statement, "compile"):
            try:
                compiled = statement.compile()
                params = getattr(compiled, "params", {}) or {}
            except Exception:
                pass

        # Repositories queries
        if "repositories" in stmt_str:
            if "repositories.github_id" in stmt_str and "SELECT repositories.github_id" in stmt_str:
                # Query for user's imported github_ids
                user_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
                ids = [
                    r.github_id
                    for r in self.repos_by_id.values()
                    if user_id is None or r.user_id == user_id
                ]
                return FakeScalarResult(ids[0] if ids else None, items=ids)

            # Check single repo query by id
            repo_id = next(
                (v for v in params.values() if isinstance(v, uuid.UUID) and v in self.repos_by_id),
                None,
            )
            if repo_id:
                repo = self.repos_by_id.get(repo_id)
                # Check user ownership if user_id is also in params
                user_ids = [v for v in params.values() if isinstance(v, uuid.UUID) and v != repo_id]
                if user_ids and repo and repo.user_id != user_ids[0]:
                    return FakeScalarResult(None, items=[])
                return FakeScalarResult(repo, items=[repo] if repo else [])

            # Check query by (user_id, github_id)
            github_id = next((v for v in params.values() if isinstance(v, int)), None)
            if github_id is not None:
                user_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
                matched = [
                    r for r in self.repos_by_id.values()
                    if r.github_id == github_id and (user_id is None or r.user_id == user_id)
                ]
                item = matched[0] if matched else None
                return FakeScalarResult(item, items=matched)

            # Query list of repos by user_id
            user_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched = [
                r for r in self.repos_by_id.values()
                if user_id is None or r.user_id == user_id
            ]
            return FakeScalarResult(matched[0] if matched else None, items=matched)

        # SyncJobs queries
        if "sync_jobs" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_jobs = [
                j for j in self.sync_jobs_by_id.values()
                if repo_id is None or j.repo_id == repo_id
            ]
            # Order by created_at desc
            matched_jobs.sort(key=lambda j: j.created_at, reverse=True)
            return FakeScalarResult(matched_jobs[0] if matched_jobs else None, items=matched_jobs)

        # Commits queries
        if "commits" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_commits = [
                c for c in self.commits_by_id.values()
                if repo_id is None or c.repo_id == repo_id
            ]
            matched_commits.sort(key=lambda c: c.committed_at, reverse=True)
            return FakeScalarResult(matched_commits[0] if matched_commits else None, items=matched_commits)

        # Pull Requests queries
        if "pull_requests" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_prs = [
                p for p in self.pulls_by_id.values()
                if repo_id is None or p.repo_id == repo_id
            ]
            matched_prs.sort(key=lambda p: p.created_at, reverse=True)
            return FakeScalarResult(matched_prs[0] if matched_prs else None, items=matched_prs)

        # Issues queries
        if "issues" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_issues = [
                i for i in self.issues_by_id.values()
                if repo_id is None or i.repo_id == repo_id
            ]
            matched_issues.sort(key=lambda i: i.created_at, reverse=True)
            return FakeScalarResult(matched_issues[0] if matched_issues else None, items=matched_issues)

        # User model queries
        where_part = stmt_str.split("WHERE", 1)[1] if "WHERE" in stmt_str else stmt_str

        if "users.github_id" in where_part:
            github_id = next((v for v in params.values() if isinstance(v, int)), None)
            user = self.users_by_github_id.get(github_id) if github_id else None
            return FakeScalarResult(user)

        if "users.id" in where_part:
            user_id = None
            for v in params.values():
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
        now = datetime.now(UTC)
        if isinstance(instance, User):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.users_by_id[instance.id] = instance
            self.users_by_github_id[instance.github_id] = instance
        elif isinstance(instance, Repository):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.repos_by_id[instance.id] = instance
        elif isinstance(instance, SyncJob):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.sync_jobs_by_id[instance.id] = instance
        elif isinstance(instance, Commit):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.commits_by_id[instance.id] = instance
        elif isinstance(instance, PullRequest):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not getattr(instance, "updated_at", None):
                instance.updated_at = now
            self.pulls_by_id[instance.id] = instance
        elif isinstance(instance, Issue):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not getattr(instance, "updated_at", None):
                instance.updated_at = now
            self.issues_by_id[instance.id] = instance

        self.added.append(instance)

    async def delete(self, instance: Any) -> None:
        if isinstance(instance, Repository) and instance.id in self.repos_by_id:
            del self.repos_by_id[instance.id]
        elif isinstance(instance, User) and instance.id in self.users_by_id:
            del self.users_by_id[instance.id]
        self.deleted.append(instance)

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
