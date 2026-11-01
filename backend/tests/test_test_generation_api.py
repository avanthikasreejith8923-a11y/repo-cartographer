"""API tests for Test Generation and File Picker endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.code_chunk import CodeChunk
from app.models.repo_file import RepoFile
from app.models.repository import Repository
from app.models.user import User
from app.services.llm import FakeLLMProvider
from tests.conftest import InMemoryAsyncSession


def create_authenticated_user(fake_db: InMemoryAsyncSession, github_id: int = 999333) -> tuple[User, dict[str, str]]:
    """Helper to persist a test user and generate session cookies."""
    user = User(
        id=uuid.uuid4(),
        github_id=github_id,
        login=f"user_{github_id}",
        name=f"User {github_id}",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}
    return user, cookies


def create_indexed_repo(
    user: User,
    fake_db: InMemoryAsyncSession,
    index_status: str = "ready",
) -> tuple[Repository, list[RepoFile]]:
    """Helper to persist an indexed repo and indexed files."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=67890,
        full_name="testuser/testgen-repo",
        default_branch="main",
        status="ready",
        index_status=index_status,
        chunk_count=5 if index_status == "ready" else 0,
    )
    fake_db.add(repo)

    f1 = RepoFile(
        id=uuid.uuid4(),
        repo_id=repo.id,
        path="app/math_ops.py",
        language="python",
        size_bytes=100,
        content_hash="hash1",
    )
    f2 = RepoFile(
        id=uuid.uuid4(),
        repo_id=repo.id,
        path="frontend/src/calculator.ts",
        language="typescript",
        size_bytes=200,
        content_hash="hash2",
    )
    fake_db.add(f1)
    fake_db.add(f2)

    # Add code chunks for math_ops.py
    c1 = CodeChunk(
        id=uuid.uuid4(),
        repo_id=repo.id,
        file_id=f1.id,
        path="app/math_ops.py",
        chunk_index=0,
        start_line=1,
        end_line=10,
        content="def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
    )
    fake_db.add(c1)

    return repo, [f1, f2]


@pytest.mark.asyncio
async def test_list_repo_files_endpoint(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/files returns list of indexed file paths, supporting q query param."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_indexed_repo(user, fake_db)

    # List all
    res_all = await client.get(f"/repos/{repo.id}/files", cookies=cookies)
    assert res_all.status_code == 200
    files = res_all.json()
    assert len(files) == 2
    assert "app/math_ops.py" in files
    assert "frontend/src/calculator.ts" in files

    # Filter with q
    res_filtered = await client.get(f"/repos/{repo.id}/files?q=math", cookies=cookies)
    assert res_filtered.status_code == 200
    filtered = res_filtered.json()
    assert len(filtered) == 1
    assert filtered[0] == "app/math_ops.py"


@pytest.mark.asyncio
async def test_generate_tests_not_indexed_returns_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/tests/generate returns 409 if repository index_status is not ready."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_indexed_repo(user, fake_db, index_status="none")

    res = await client.post(
        f"/repos/{repo.id}/tests/generate",
        json={"path": "app/math_ops.py"},
        cookies=cookies,
    )
    assert res.status_code == 409
    assert "not ready" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_tests_file_not_found_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/tests/generate returns 404 if file path is not indexed."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_indexed_repo(user, fake_db, index_status="ready")

    res = await client.post(
        f"/repos/{repo.id}/tests/generate",
        json={"path": "nonexistent/file.py"},
        cookies=cookies,
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_tests_success_and_history(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/tests/generate generates tests draft, stores in DB, and returns history."""
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_indexed_repo(user, fake_db, index_status="ready")

    with patch("app.services.test_generation.get_llm_provider", return_value=FakeLLMProvider(mode="tests")):
        # Generate test
        gen_res = await client.post(
            f"/repos/{repo.id}/tests/generate",
            json={"path": "app/math_ops.py"},
            cookies=cookies,
        )
        assert gen_res.status_code == 200
        test_data = gen_res.json()
        assert test_data["path"] == "app/math_ops.py"
        assert test_data["framework"] == "pytest"
        assert "def test_sample_behavior():" in test_data["content"]
        assert test_data["syntax_valid"] is True
        test_id = test_data["id"]

        # History GET
        hist_res = await client.get(f"/repos/{repo.id}/tests", cookies=cookies)
        assert hist_res.status_code == 200
        hist_list = hist_res.json()
        assert len(hist_list) == 1
        assert hist_list[0]["id"] == test_id

        # Delete test
        del_res = await client.delete(f"/repos/{repo.id}/tests/{test_id}", cookies=cookies)
        assert del_res.status_code == 204

        # Verify deleted
        hist_res2 = await client.get(f"/repos/{repo.id}/tests", cookies=cookies)
        assert len(hist_res2.json()) == 0


@pytest.mark.asyncio
async def test_generate_tests_other_user_repo_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/tests/generate returns 404 for repositories owned by other users."""
    owner_user, _ = create_authenticated_user(fake_db, github_id=444111)
    other_user, other_cookies = create_authenticated_user(fake_db, github_id=444222)
    repo, _ = create_indexed_repo(owner_user, fake_db, index_status="ready")

    res = await client.post(
        f"/repos/{repo.id}/tests/generate",
        json={"path": "app/math_ops.py"},
        cookies=other_cookies,
    )
    assert res.status_code == 404
    assert "Repository not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_generate_tests_rate_limit_exceeded_returns_429(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/tests/generate returns 429 when rate limit is exceeded."""
    from fastapi import HTTPException
    user, cookies = create_authenticated_user(fake_db)
    repo, _ = create_indexed_repo(user, fake_db, index_status="ready")

    with patch("app.services.test_generation.check_rate_limit", side_effect=HTTPException(status_code=429, detail="Rate limit exceeded.")):
        res = await client.post(
            f"/repos/{repo.id}/tests/generate",
            json={"path": "app/math_ops.py"},
            cookies=cookies,
        )
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

