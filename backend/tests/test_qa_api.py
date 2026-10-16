"""API tests for Codebase Q&A and Documentation Generation endpoints using FakeLLMProvider."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.code_chunk import CodeChunk
from app.models.qa_history import QAHistory
from app.models.repo_doc import RepoDoc
from app.models.repository import Repository
from app.models.user import User
from app.services.llm import FakeLLMProvider
from tests.conftest import InMemoryAsyncSession


def create_authenticated_user(fake_db: InMemoryAsyncSession, github_id: int = 999888) -> tuple[User, dict[str, str]]:
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


def create_indexed_repository(user: User, fake_db: InMemoryAsyncSession, index_status: str = "ready") -> Repository:
    """Helper to persist a repository with an indexed status."""
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=123456,
        full_name="testuser/indexed-repo",
        default_branch="main",
        indexed_commit_sha="a" * 40,
        status="ready",
        index_status=index_status,
        chunk_count=10 if index_status == "ready" else 0,
    )
    fake_db.add(repo)
    return repo


@pytest.mark.asyncio
async def test_ask_question_success(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/ask returns grounded answer and cited sources using FakeLLMProvider."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    # Add a code chunk to fake_db for search retrieval
    chunk = CodeChunk(
        id=uuid.uuid4(),
        repo_id=repo.id,
        path="app/main.py",
        start_line=1,
        end_line=25,
        content="app = FastAPI(title='Repo Cartographer')",
        symbol="app",
        language="python",
        kind="statement",
    )
    fake_db.add(chunk)

    with patch("app.api.routes.repos.ask_codebase") as mock_ask:
        from app.services.qa import AskResult

        mock_ask.return_value = AskResult(
            answer="The application entry point creates the FastAPI instance [S1].",
            status="ok",
            citations_missing=False,
            sources=[
                {
                    "marker": "[S1]",
                    "path": "app/main.py",
                    "start_line": 1,
                    "end_line": 25,
                    "symbol": "app",
                    "language": "python",
                    "snippet": "app = FastAPI(title='Repo Cartographer')",
                    "permalink": f"https://github.com/{repo.full_name}/blob/{repo.indexed_commit_sha}/app/main.py#L1-L25",
                }
            ],
            all_retrieved_sources=[],
            history_id=uuid.uuid4(),
            latency_ms=120,
        )

        resp = await client.post(
            f"/repos/{repo.id}/ask",
            json={"question": "Where is the FastAPI app configured?"},
            cookies=cookies,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "FastAPI instance [S1]" in data["answer"]
        assert data["status"] == "ok"
        assert data["citations_missing"] is False
        assert len(data["sources"]) == 1
        assert data["sources"][0]["marker"] == "[S1]"
        assert data["sources"][0]["path"] == "app/main.py"
        assert data["latency_ms"] == 120


@pytest.mark.asyncio
async def test_ask_question_insufficient_evidence(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/ask returns insufficient_evidence and skips LLM when nothing relevant found."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    # Mock execute_code_search returning empty list
    with patch("app.services.qa.execute_code_search", return_value=[]):
        resp = await client.post(
            f"/repos/{repo.id}/ask",
            json={"question": "Something completely nonexistent in the codebase?"},
            cookies=cookies,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "insufficient_evidence"
        assert "could not find any relevant code snippets" in data["answer"].lower()
        assert data["sources"] == []
        assert data["history_id"] is not None


@pytest.mark.asyncio
async def test_ask_question_not_indexed_returns_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/ask returns HTTP 409 Conflict if repo is not indexed."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="not_indexed")

    resp = await client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "How does this code work?"},
        cookies=cookies,
    )
    assert resp.status_code == 409
    assert "not been indexed yet" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ask_question_other_user_repo_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/ask on another user's repo returns HTTP 404."""
    user1, cookies1 = create_authenticated_user(fake_db, github_id=111)
    user2, cookies2 = create_authenticated_user(fake_db, github_id=222)

    repo_user2 = create_indexed_repository(user2, fake_db, index_status="ready")

    resp = await client.post(
        f"/repos/{repo_user2.id}/ask",
        json={"question": "What is in this repo?"},
        cookies=cookies1,  # User 1 attempting to access user 2's repo
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Repository not found"


@pytest.mark.asyncio
async def test_ask_question_rate_limit_exceeded_returns_429(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/ask returns HTTP 429 when rate limit is exceeded."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    with patch("app.services.qa.check_rate_limit") as mock_rl:
        from fastapi import HTTPException

        mock_rl.side_effect = HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 10 questions per minute.",
            headers={"Retry-After": "45"},
        )

        resp = await client.post(
            f"/repos/{repo.id}/ask",
            json={"question": "Question over limit?"},
            cookies=cookies,
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]
        assert resp.headers.get("Retry-After") == "45"


@pytest.mark.asyncio
async def test_qa_history_list_and_delete(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/ask/history lists records, and DELETE removes them."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    hist1 = QAHistory(
        id=uuid.uuid4(),
        repo_id=repo.id,
        user_id=user.id,
        question="What is this?",
        answer="A service [S1].",
        citations=[{"marker": "[S1]", "path": "main.py"}],
        status="ok",
        model="fake-llm",
        latency_ms=100,
    )
    hist2 = QAHistory(
        id=uuid.uuid4(),
        repo_id=repo.id,
        user_id=user.id,
        question="Another question?",
        answer="Another answer.",
        citations=[],
        status="insufficient_evidence",
        model="fake-llm",
        latency_ms=50,
    )
    fake_db.add(hist1)
    fake_db.add(hist2)

    # 1. List history
    resp = await client.get(f"/repos/{repo.id}/ask/history?limit=20", cookies=cookies)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    ids = [i["id"] for i in items]
    assert str(hist1.id) in ids
    assert str(hist2.id) in ids

    # 2. Delete history record 1
    del_resp = await client.delete(f"/repos/{repo.id}/ask/history/{hist1.id}", cookies=cookies)
    assert del_resp.status_code == 200
    assert del_resp.json() == {"deleted": True}

    # 3. Verify history list now only contains record 2
    resp_after = await client.get(f"/repos/{repo.id}/ask/history?limit=20", cookies=cookies)
    items_after = resp_after.json()
    assert len(items_after) == 1
    assert items_after[0]["id"] == str(hist2.id)


@pytest.mark.asyncio
async def test_doc_generate_and_get_flow(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/docs/{doc_type}/generate enqueues doc job and GET retrieves status."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    with patch("app.api.routes.repos.enqueue_doc_job", return_value="job-doc-123"):
        # 1. Trigger architecture generation
        gen_resp = await client.post(
            f"/repos/{repo.id}/docs/architecture/generate",
            cookies=cookies,
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["doc_type"] == "architecture"
        assert gen_data["status"] == "pending"

        # 2. GET documentation before worker finishes
        get_resp = await client.get(
            f"/repos/{repo.id}/docs/architecture",
            cookies=cookies,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["status"] == "pending"
        assert get_data["doc_type"] == "architecture"

        # 3. Simulate worker finishing doc generation
        existing_doc = fake_db.repo_docs_by_id.get(uuid.UUID(gen_data["id"]))
        assert existing_doc is not None
        existing_doc.status = "ready"
        existing_doc.content_markdown = "# Architecture Overview\n\nMain components [S1]."
        existing_doc.citations = [{"marker": "[S1]", "path": "app/main.py"}]

        # 4. GET documentation after completion
        get_ready = await client.get(
            f"/repos/{repo.id}/docs/architecture",
            cookies=cookies,
        )
        assert get_ready.status_code == 200
        ready_data = get_ready.json()
        assert ready_data["status"] == "ready"
        assert "Architecture Overview" in ready_data["content_markdown"]
        assert len(ready_data["citations"]) == 1


@pytest.mark.asyncio
async def test_doc_generate_conflict_when_already_generating(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/docs/{doc_type}/generate returns 409 if status is already 'generating'."""
    user, cookies = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    doc = RepoDoc(
        id=uuid.uuid4(),
        repo_id=repo.id,
        doc_type="readme",
        status="generating",
    )
    fake_db.add(doc)

    resp = await client.post(
        f"/repos/{repo.id}/docs/readme/generate",
        cookies=cookies,
    )
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_doc_generation_failed_job_updates_status(
    fake_db: InMemoryAsyncSession,
):
    """execute_doc_generation marks RepoDoc as 'failed' on unhandled error without stuck generating."""
    from app.services.doc_generator import execute_doc_generation

    user, _ = create_authenticated_user(fake_db)
    repo = create_indexed_repository(user, fake_db, index_status="ready")

    failing_llm = FakeLLMProvider()
    failing_llm.generate = AsyncMock(side_effect=RuntimeError("LLM out of quota"))

    with pytest.raises(RuntimeError, match="LLM out of quota"):
        await execute_doc_generation(
            repo_id=repo.id,
            doc_type="architecture",
            db=fake_db,
            llm_provider=failing_llm,
        )

    # Check that repo_doc status was set to 'failed'
    matched_doc = next(
        (d for d in fake_db.repo_docs_by_id.values() if d.repo_id == repo.id and d.doc_type == "architecture"),
        None,
    )
    assert matched_doc is not None
    assert matched_doc.status == "failed"
    assert "LLM out of quota" in (matched_doc.error or "")
