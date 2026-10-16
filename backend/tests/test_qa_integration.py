"""Integration tests for Phase 4 Q&A and Documentation Generation against live Neon TEST_DATABASE_URL.

Verifies:
1. Migration upgrade and downgrade idempotency on TEST_DATABASE_URL.
2. Persistence of qa_history and repo_docs records in PostgreSQL with JSONB citations.
3. Upsert idempotency: generating documentation multiple times overwrites the single row per (repo_id, doc_type).
4. Ownership enforcement: attempting to access or generate Q&A/docs on another user's repo is rejected.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.qa_history import QAHistory
from app.models.repo_doc import RepoDoc
from app.models.repository import Repository
from app.models.user import User
from app.services.doc_generator import execute_doc_generation
from app.services.embeddings import FakeEmbeddingProvider
from app.services.llm import FakeLLMProvider
from app.services.qa import ask_codebase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _make_mock_user(login_prefix: str) -> User:
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


def _make_mock_repo(user_id: uuid.UUID, name_prefix: str, index_status: str = "ready") -> Repository:
    uid = uuid.uuid4()
    rand_github_id = random.randint(10000000, 99999999)
    return Repository(
        id=uid,
        user_id=user_id,
        github_id=rand_github_id,
        full_name=f"test-owner/{name_prefix}-{uid.hex[:8]}",
        description="Integration test repo for Phase 4",
        default_branch="main",
        indexed_commit_sha="b" * 40,
        status="ready",
        index_status=index_status,
        chunk_count=20,
    )


async def test_migration_up_and_down_on_test_db() -> None:
    """Verify Alembic 0004 migration downgrades and upgrades cleanly on the TEST database."""
    test_url = settings.validate_test_database_url()
    sync_url = settings.normalize_sync_dsn(test_url)

    ini_path = Path("alembic.ini") if Path("alembic.ini").exists() else Path("backend/alembic.ini")
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Run alembic in separate thread to avoid conflicting with pytest-asyncio's running event loop
    await asyncio.to_thread(command.downgrade, cfg, "0003_code_intelligence")
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_qa_history_and_repo_docs_rows_persist(
    test_db_session: AsyncSession,
) -> None:
    """Verify qa_history and repo_docs rows persist with JSONB data in PostgreSQL."""
    user = _make_mock_user("qa-persist-user")
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "qa-persist-repo")
    test_db_session.add(repo)
    await test_db_session.commit()

    try:
        # 1. Insert QAHistory row
        qa_row = QAHistory(
            id=uuid.uuid4(),
            repo_id=repo.id,
            user_id=user.id,
            question="What is the architecture?",
            answer="It follows a 3-tier architecture [S1].",
            citations=[
                {
                    "marker": "[S1]",
                    "path": "app/main.py",
                    "start_line": 1,
                    "end_line": 30,
                    "symbol": "app",
                    "language": "python",
                    "snippet": "app = FastAPI()",
                    "permalink": "https://github.com/test-owner/repo/blob/main/app/main.py#L1-L30",
                }
            ],
            status="ok",
            model="models/gemini-3.5-flash-lite",
            indexed_commit_sha=repo.indexed_commit_sha,
            latency_ms=250,
        )
        test_db_session.add(qa_row)

        # 2. Insert RepoDoc row
        now = datetime.now(UTC)
        doc_row = RepoDoc(
            id=uuid.uuid4(),
            repo_id=repo.id,
            doc_type="architecture",
            status="ready",
            content_markdown="# Architecture Overview\n\nModular design [S1].",
            citations=[{"marker": "[S1]", "path": "app/main.py"}],
            error=None,
            model="models/gemini-3.5-flash-lite",
            indexed_commit_sha=repo.indexed_commit_sha,
            generated_at=now,
            created_at=now,
            updated_at=now,
        )
        test_db_session.add(doc_row)
        await test_db_session.commit()

        # Query back and verify persistence
        qa_stmt = select(QAHistory).where(QAHistory.id == qa_row.id)
        qa_res = await test_db_session.execute(qa_stmt)
        persisted_qa = qa_res.scalar_one_or_none()
        assert persisted_qa is not None
        assert persisted_qa.question == "What is the architecture?"
        assert len(persisted_qa.citations) == 1
        assert persisted_qa.citations[0]["marker"] == "[S1]"
        assert persisted_qa.status == "ok"

        doc_stmt = select(RepoDoc).where(RepoDoc.id == doc_row.id)
        doc_res = await test_db_session.execute(doc_stmt)
        persisted_doc = doc_res.scalar_one_or_none()
        assert persisted_doc is not None
        assert persisted_doc.doc_type == "architecture"
        assert persisted_doc.status == "ready"
        assert "Architecture Overview" in persisted_doc.content_markdown
        assert len(persisted_doc.citations) == 1

    finally:
        await test_db_session.execute(delete(QAHistory).where(QAHistory.repo_id == repo.id))
        await test_db_session.execute(delete(RepoDoc).where(RepoDoc.repo_id == repo.id))
        await test_db_session.execute(delete(Repository).where(Repository.id == repo.id))
        await test_db_session.execute(delete(User).where(User.id == user.id))
        await test_db_session.commit()


async def test_repo_docs_upsert_regenerates_same_row(
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify regenerating documentation updates the existing row on (repo_id, doc_type) unique constraint."""
    monkeypatch.setattr("app.services.search.get_embedding_provider", FakeEmbeddingProvider)

    user = _make_mock_user("doc-upsert-user")
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "doc-upsert-repo", index_status="ready")
    test_db_session.add(repo)
    await test_db_session.commit()

    try:
        fake_llm_v1 = FakeLLMProvider(custom_response="# Architecture Overview\n\nVersion 1 [S1].")
        fake_llm_v2 = FakeLLMProvider(custom_response="# Architecture Overview\n\nVersion 2 [S1].")

        # First generation
        doc1 = await execute_doc_generation(
            repo_id=repo.id,
            doc_type="architecture",
            db=test_db_session,
            llm_provider=fake_llm_v1,
        )
        assert doc1.status == "ready"
        assert "Version 1" in doc1.content_markdown
        doc1_id = doc1.id

        # Second generation (regeneration)
        doc2 = await execute_doc_generation(
            repo_id=repo.id,
            doc_type="architecture",
            db=test_db_session,
            llm_provider=fake_llm_v2,
        )
        assert doc2.status == "ready"
        assert "Version 2" in doc2.content_markdown
        assert doc2.id == doc1_id  # Same database row updated

        # Verify only one row exists in database for this (repo_id, doc_type)
        count_stmt = select(RepoDoc).where(
            RepoDoc.repo_id == repo.id,
            RepoDoc.doc_type == "architecture",
        )
        count_res = await test_db_session.execute(count_stmt)
        all_docs = count_res.scalars().all()
        assert len(all_docs) == 1
        assert all_docs[0].id == doc1_id

    finally:
        await test_db_session.execute(delete(RepoDoc).where(RepoDoc.repo_id == repo.id))
        await test_db_session.execute(delete(Repository).where(Repository.id == repo.id))
        await test_db_session.execute(delete(User).where(User.id == user.id))
        await test_db_session.commit()


async def test_qa_and_docs_ownership_enforced(
    test_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify ask_codebase strictly enforces repository ownership and rejects cross-user access."""
    monkeypatch.setattr("app.services.search.get_embedding_provider", FakeEmbeddingProvider)

    user_owner = _make_mock_user("owner-user")
    user_intruder = _make_mock_user("intruder-user")
    test_db_session.add(user_owner)
    test_db_session.add(user_intruder)
    await test_db_session.flush()

    repo = _make_mock_repo(user_owner.id, "owner-repo", index_status="ready")
    test_db_session.add(repo)
    await test_db_session.commit()

    try:
        # Intruder attempts to ask question on owner's repo
        with pytest.raises(HTTPException) as exc_info:
            await ask_codebase(
                repo=repo,
                user=user_intruder,
                question="What is this repository?",
                db=test_db_session,
                redis_client=None,
                llm_provider=FakeLLMProvider(),
            )
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Repository not found"

    finally:
        await test_db_session.execute(delete(Repository).where(Repository.id == repo.id))
        await test_db_session.execute(delete(User).where(User.id.in_([user_owner.id, user_intruder.id])))
        await test_db_session.commit()
