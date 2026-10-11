"""Integration tests for codebase indexing, incremental diffing, and hybrid search against live Neon TEST_DATABASE_URL.

Verifies:
1. Double-index idempotency: running indexing twice against live PostgreSQL leaves identical row counts in repo_files and code_chunks.
2. Incremental diffing: file modification replaces old chunks, deleted file cascades deletion of chunks, new files are added.
3. Hybrid, semantic, and keyword search execution with real pgvector and tsvector operations.
4. Cross-user access control: attempting to index or search another user's repo returns 404.
"""

from __future__ import annotations

import hashlib
import uuid

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.code_chunk import CodeChunk
from app.models.index_job import IndexJob
from app.models.repo_file import RepoFile
from app.models.repository import Repository
from app.models.user import User
from app.services.embeddings import FakeEmbeddingProvider
from app.services.indexer import execute_repo_indexing
from app.services.repo_fetcher import FetchedFile
from app.services.search import execute_code_search

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _make_mock_user(login_prefix: str) -> User:
    import random
    uid = uuid.uuid4()
    rand_github_id = random.randint(10000000, 99999999)
    login = f"{login_prefix}-{uid.hex[:8]}"
    return User(
        id=uid,
        github_id=rand_github_id,
        login=login,
        name=f"Test {login}",
        email=f"{login}@example.com",
        avatar_url="https://avatars.githubusercontent.com/u/1?v=4",
        encrypted_access_token=encrypt_token("ghp_demo_integration_testing_token"),
    )


def _make_mock_repo(user_id: uuid.UUID, name_prefix: str) -> Repository:
    import random
    uid = uuid.uuid4()
    rand_github_id = random.randint(10000000, 99999999)
    return Repository(
        id=uid,
        user_id=user_id,
        github_id=rand_github_id,
        full_name=f"test-owner/{name_prefix}-{uid.hex[:8]}",
        description="Integration test repo for indexing",
        default_branch="main",
        status="ready",
        index_status="none",
        chunk_count=0,
    )


def _make_fetched_file(path: str, content: str, language: str) -> FetchedFile:
    content_bytes = content.encode("utf-8")
    return FetchedFile(
        path=path,
        content=content,
        size_bytes=len(content_bytes),
        content_hash=hashlib.sha256(content_bytes).hexdigest(),
        language=language,
    )


async def _cleanup_repo_index(session: AsyncSession, repo_id: uuid.UUID) -> None:
    """Clean up indexed chunks, files, jobs, and repo."""
    await session.execute(delete(CodeChunk).where(CodeChunk.repo_id == repo_id))
    await session.execute(delete(RepoFile).where(RepoFile.repo_id == repo_id))
    await session.execute(delete(IndexJob).where(IndexJob.repo_id == repo_id))
    await session.execute(delete(Repository).where(Repository.id == repo_id))
    await session.commit()


async def test_indexing_idempotency_double_run(
    test_db_session: AsyncSession,
    monkeypatch,
) -> None:
    """Verify running indexing twice on identical files yields identical row counts in PostgreSQL."""
    user = _make_mock_user("index-idemp-user")
    user_id = user.id
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "index-idemp-repo")
    repo_id = repo.id
    test_db_session.add(repo)
    await test_db_session.commit()

    sample_files = [
        _make_fetched_file(
            "src/math.py",
            "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
            "python",
        ),
        _make_fetched_file(
            "README.md",
            "# Math Package\nUtility functions for arithmetic operations.\n",
            "markdown",
        ),
    ]

    # Monkeypatch fetch_repository_files to return sample_files
    async def _mock_fetch(*args, **kwargs):
        return sample_files

    monkeypatch.setattr("app.services.indexer.fetch_repository_files", _mock_fetch)
    monkeypatch.setattr("app.services.indexer._get_sample_repo_files", lambda: sample_files)

    provider = FakeEmbeddingProvider(dimension=768)

    try:
        # First index run
        job1 = await execute_repo_indexing(
            repo_id=repo.id,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert job1.status == "completed"
        assert repo.index_status == "ready"

        # Check row counts after run 1
        files_q1 = await test_db_session.execute(
            select(func.count(RepoFile.id)).where(RepoFile.repo_id == repo.id)
        )
        files_count_1 = files_q1.scalar()

        chunks_q1 = await test_db_session.execute(
            select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo.id)
        )
        chunks_count_1 = chunks_q1.scalar()

        assert files_count_1 == 2
        assert chunks_count_1 > 0
        assert repo.chunk_count == chunks_count_1

        # Second index run with identical files
        job2 = await execute_repo_indexing(
            repo_id=repo.id,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert job2.status == "completed"
        assert job2.stats["new_chunks"] == 0
        assert job2.stats["unchanged_files"] == 2

        # Verify row counts remain strictly identical
        files_q2 = await test_db_session.execute(
            select(func.count(RepoFile.id)).where(RepoFile.repo_id == repo.id)
        )
        files_count_2 = files_q2.scalar()

        chunks_q2 = await test_db_session.execute(
            select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo.id)
        )
        chunks_count_2 = chunks_q2.scalar()

        assert files_count_2 == files_count_1
        assert chunks_count_2 == chunks_count_1

    finally:
        await _cleanup_repo_index(test_db_session, repo_id)
        await test_db_session.execute(delete(User).where(User.id == user_id))
        await test_db_session.commit()


async def test_indexing_incremental_diff_and_search_modes(
    test_db_session: AsyncSession,
    monkeypatch,
) -> None:
    """Verify file modification, deletion, and real pgvector & full-text search against Neon."""
    user = _make_mock_user("diff-search-user")
    user_id = user.id
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "diff-search-repo")
    repo_id = repo.id
    test_db_session.add(repo)
    await test_db_session.commit()

    file_a = _make_fetched_file(
        "src/calculator.py",
        "def calculate_total(prices: list[float]) -> float:\n    \"\"\"Calculate total price.\"\"\"\n    return sum(prices)\n",
        "python",
    )
    file_b = _make_fetched_file(
        "src/deprecated.py",
        "# To be deleted soon\nx = 100\n",
        "python",
    )

    current_files = [file_a, file_b]
    monkeypatch.setattr("app.services.indexer.fetch_repository_files", lambda *args, **kwargs: current_files)
    monkeypatch.setattr("app.services.indexer._get_sample_repo_files", lambda: current_files)

    provider = FakeEmbeddingProvider(dimension=768)

    try:
        # Step 1: Initial Indexing
        await execute_repo_indexing(repo_id=repo.id, db=test_db_session, embedding_provider=provider)

        initial_files_count = (
            await test_db_session.execute(select(func.count(RepoFile.id)).where(RepoFile.repo_id == repo.id))
        ).scalar()
        assert initial_files_count == 2

        # Step 2: Incremental update
        # file_a is modified, file_b is deleted, file_c is added
        file_a_modified = _make_fetched_file(
            "src/calculator.py",
            "def calculate_total(prices: list[float], tax_rate: float = 0.05) -> float:\n    \"\"\"Calculate total price with tax.\"\"\"\n    return sum(prices) * (1.0 + tax_rate)\n",
            "python",
        )
        file_c_new = _make_fetched_file(
            "src/utils.py",
            "def format_currency(amount: float) -> str:\n    return f'${amount:.2f}'\n",
            "python",
        )
        current_files = [file_a_modified, file_c_new]

        job_diff = await execute_repo_indexing(
            repo_id=repo.id,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert job_diff.status == "completed"
        assert job_diff.stats["deleted_files"] == 1
        assert job_diff.stats["modified_files"] == 1
        assert job_diff.stats["new_files"] == 1

        # Check deprecated.py was deleted
        del_check = (
            await test_db_session.execute(
                select(RepoFile).where(RepoFile.repo_id == repo.id, RepoFile.path == "src/deprecated.py")
            )
        ).scalar_one_or_none()
        assert del_check is None

        # Step 3: Hybrid, Semantic, and Keyword Search
        # Refresh repo
        await test_db_session.refresh(repo)

        # 3a. Keyword Search
        kw_results = await execute_code_search(
            repo=repo,
            query="calculate_total",
            mode="keyword",
            limit=5,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert len(kw_results) > 0
        assert any("calculate_total" in r.snippet for r in kw_results)
        assert kw_results[0].permalink.startswith("https://github.com/")

        # 3b. Semantic Search
        sem_results = await execute_code_search(
            repo=repo,
            query="calculate sum of prices with tax",
            mode="semantic",
            limit=5,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert len(sem_results) > 0

        # 3c. Hybrid Search (RRF)
        hybrid_results = await execute_code_search(
            repo=repo,
            query="calculate_total tax",
            mode="hybrid",
            limit=5,
            db=test_db_session,
            embedding_provider=provider,
        )
        assert len(hybrid_results) > 0
        assert hybrid_results[0].path in ("src/calculator.py", "src/utils.py")

    finally:
        await _cleanup_repo_index(test_db_session, repo_id)
        await test_db_session.execute(delete(User).where(User.id == user_id))
        await test_db_session.commit()


async def test_cross_user_indexing_and_search_access_control(
    test_db_session: AsyncSession,
) -> None:
    """Verify User B cannot trigger indexing or search on User A's repository (HTTP 404)."""
    user_a = _make_mock_user("owner-user-a")
    user_b = _make_mock_user("attacker-user-b")
    user_a_id = user_a.id
    user_b_id = user_b.id
    test_db_session.add(user_a)
    test_db_session.add(user_b)
    await test_db_session.flush()

    repo_a = _make_mock_repo(user_a_id, "private-repo")
    repo_a.index_status = "ready"
    repo_a_id = repo_a.id
    test_db_session.add(repo_a)
    await test_db_session.commit()

    # User B credentials
    token_b = create_session_token({"sub": str(user_b.id)})
    cookies_b = {settings.SESSION_COOKIE_NAME: token_b}

    # Use HTTP client with app overriding get_db to use test_db_session
    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: test_db_session

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # User B attempts to index User A's repo -> 404
            res_index = await client.post(f"/repos/{repo_a.id}/index", cookies=cookies_b)
            assert res_index.status_code == 404
            assert res_index.json()["detail"] == "Repository not found"

            # User B attempts to get index-status for User A's repo -> 404
            res_status = await client.get(f"/repos/{repo_a.id}/index-status", cookies=cookies_b)
            assert res_status.status_code == 404

            # User B attempts to search User A's repo -> 404
            res_search = await client.post(
                f"/repos/{repo_a.id}/search",
                json={"query": "secret_function", "mode": "hybrid"},
                cookies=cookies_b,
            )
            assert res_search.status_code == 404
            assert res_search.json()["detail"] == "Repository not found"

    finally:
        app.dependency_overrides.clear()
        await _cleanup_repo_index(test_db_session, repo_a_id)
        await test_db_session.execute(delete(User).where(User.id.in_([user_a_id, user_b_id])))
        await test_db_session.commit()
