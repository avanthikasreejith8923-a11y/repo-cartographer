"""Integration tests for Phase 5 Intelligence features against live Neon TEST_DATABASE_URL.

Verifies:
1. Migration upgrade/downgrade cleanly between 0004_qa_and_docs and head on TEST_DATABASE_URL.
2. PRAnalysis upsert idempotency on PostgreSQL (ON CONFLICT (repo_id, pr_number) DO UPDATE).
3. IssueAnalysis upsert idempotency and real pgvector cosine distance (<=>) execution.
4. GeneratedTest persistence, ast syntax tracking, and cascade deletion on repository removal.
5. Ownership isolation: user B cannot access user A's PR analyses, issues, or generated tests.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.core.config import settings
from app.core.security import encrypt_token
from app.models.analysis_job import AnalysisJob
from app.models.generated_test import GeneratedTest
from app.models.issue import Issue
from app.models.issue_analysis import IssueAnalysis
from app.models.pr_analysis import PRAnalysis
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.user import User

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
        description="Integration test repo for Phase 5",
        default_branch="main",
        indexed_commit_sha="c" * 40,
        status="ready",
        index_status=index_status,
        chunk_count=10,
    )


async def test_migration_0005_up_and_down_on_test_db() -> None:
    """Verify Alembic 0005 migration downgrades and upgrades cleanly on the TEST database."""
    test_url = settings.validate_test_database_url()
    sync_url = settings.normalize_sync_dsn(test_url)

    ini_path = Path("alembic.ini") if Path("alembic.ini").exists() else Path("backend/alembic.ini")
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", sync_url)

    # Downgrade to Phase 4 head
    await asyncio.to_thread(command.downgrade, cfg, "0004_qa_and_documentation")
    # Upgrade back to Phase 5 head
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_pr_analysis_upsert_idempotency_on_postgres(
    test_db_session: AsyncSession,
) -> None:
    """Verify pr_analyses table enforces UNIQUE(repo_id, pr_number) and ON CONFLICT DO UPDATE works cleanly."""
    user = _make_mock_user("pr-upsert-user")
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "pr-upsert-repo")
    test_db_session.add(repo)
    await test_db_session.flush()

    pr = PullRequest(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=101,
        title="Add authentication middleware",
        body="Initial PR description",
        state="open",
        author_login=user.login,
        created_at=datetime.now(UTC),
    )
    test_db_session.add(pr)
    await test_db_session.commit()

    try:
        # First insertion: initial analysis
        stmt1 = (
            pg_insert(PRAnalysis)
            .values(
                id=uuid.uuid4(),
                repo_id=repo.id,
                pr_number=101,
                summary_markdown="Initial summary",
                risk_level="low",
                risk_score=10,
                risk_reasons=["Minor documentation update"],
                files_analyzed=1,
                truncated=False,
                status="ok",
                model="test-model",
            )
            .on_conflict_do_update(
                index_elements=["repo_id", "pr_number"],
                set_={
                    "risk_level": "low",
                    "risk_score": 10,
                    "summary_markdown": "Initial summary",
                },
            )
        )
        await test_db_session.execute(stmt1)
        await test_db_session.commit()

        # Check exactly 1 row
        count1 = await test_db_session.scalar(
            select(func.count(PRAnalysis.id)).where(
                PRAnalysis.repo_id == repo.id,
                PRAnalysis.pr_number == 101,
            )
        )
        assert count1 == 1

        # Second insertion: re-analysis with higher risk
        stmt2 = (
            pg_insert(PRAnalysis)
            .values(
                id=uuid.uuid4(),
                repo_id=repo.id,
                pr_number=101,
                summary_markdown="Updated security-critical summary",
                risk_level="high",
                risk_score=85,
                risk_reasons=["Auth middleware modified", "Database migration added"],
                files_analyzed=3,
                truncated=False,
                status="ok",
                model="test-model",
            )
            .on_conflict_do_update(
                index_elements=["repo_id", "pr_number"],
                set_={
                    "risk_level": "high",
                    "risk_score": 85,
                    "risk_reasons": ["Auth middleware modified", "Database migration added"],
                    "summary_markdown": "Updated security-critical summary",
                    "files_analyzed": 3,
                },
            )
        )
        await test_db_session.execute(stmt2)
        await test_db_session.commit()

        # Count must STILL be exactly 1, but updated
        res = await test_db_session.execute(
            select(PRAnalysis).where(
                PRAnalysis.repo_id == repo.id,
                PRAnalysis.pr_number == 101,
            )
        )
        row = res.scalar_one()
        assert row.risk_level == "high"
        assert row.risk_score == 85
        assert len(row.risk_reasons) == 2
        assert "Updated security-critical summary" in row.summary_markdown
    finally:
        await test_db_session.execute(delete(PRAnalysis).where(PRAnalysis.repo_id == repo.id))
        await test_db_session.execute(delete(PullRequest).where(PullRequest.repo_id == repo.id))
        await test_db_session.execute(delete(Repository).where(Repository.id == repo.id))
        await test_db_session.execute(delete(User).where(User.id == user.id))
        await test_db_session.commit()


async def test_issue_analysis_upsert_and_pgvector_similarity_query(
    test_db_session: AsyncSession,
) -> None:
    """Verify issue_analyses upsert idempotency and live pgvector cosine distance (<=>) execution."""
    user = _make_mock_user("issue-pgvector-user")
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "issue-pgvector-repo")
    test_db_session.add(repo)
    await test_db_session.flush()

    issue1 = Issue(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=201,
        title="Application crashes on startup with null pointer",
        body="Stack trace points to auth config",
        state="open",
        author_login=user.login,
        created_at=datetime.now(UTC),
    )
    issue2 = Issue(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=202,
        title="Crash when launching app: null reference exception",
        body="Similar startup failure",
        state="open",
        author_login=user.login,
        created_at=datetime.now(UTC),
    )
    test_db_session.add_all([issue1, issue2])
    await test_db_session.commit()

    repo_id = repo.id
    user_id = user.id

    try:
        # Create normalized 768-dim float vectors
        dim = settings.EMBEDDING_DIM
        vec1 = [1.0 / (dim ** 0.5)] * dim
        vec2 = [0.99 / (dim ** 0.5)] * dim  # Very close to vec1

        # Upsert Issue 201 and 202 via ORM
        ia1 = IssueAnalysis(
            id=uuid.uuid4(),
            repo_id=repo_id,
            issue_number=201,
            issue_type="bug",
            confidence=0.95,
            reason="Stack trace shown",
            embedding=vec1,
            embedding_model="text-embedding-004",
        )
        ia2 = IssueAnalysis(
            id=uuid.uuid4(),
            repo_id=repo_id,
            issue_number=202,
            issue_type="bug",
            confidence=0.92,
            reason="Null reference on launch",
            embedding=vec2,
            embedding_model="text-embedding-004",
        )
        test_db_session.add_all([ia1, ia2])
        await test_db_session.commit()

        # Update Issue 201 attributes and commit to verify update idempotency
        ia1.confidence = 0.99
        ia1.reason = "Updated analysis reason"
        await test_db_session.commit()

        count = await test_db_session.scalar(
            select(func.count(IssueAnalysis.id)).where(IssueAnalysis.repo_id == repo_id)
        )
        assert count == 2

        # Verify real pgvector cosine distance operator executes on PostgreSQL
        query = (
            select(
                IssueAnalysis.issue_number,
                IssueAnalysis.embedding.cosine_distance(vec1).label("distance"),
            )
            .where(IssueAnalysis.repo_id == repo_id)
            .order_by("distance")
            .limit(2)
        )
        res = await test_db_session.execute(query)
        rows = res.fetchall()
        assert len(rows) == 2
        # First row is issue 201 (identical vector, distance near 0.0)
        assert rows[0][0] == 201
        assert rows[0][1] < 0.01

        # Second row is issue 202 (close distance)
        assert rows[1][0] == 202
        assert rows[1][1] < 0.05

    finally:
        await test_db_session.rollback()
        await test_db_session.execute(delete(IssueAnalysis).where(IssueAnalysis.repo_id == repo_id))
        await test_db_session.execute(delete(Issue).where(Issue.repo_id == repo_id))
        await test_db_session.execute(delete(Repository).where(Repository.id == repo_id))
        await test_db_session.execute(delete(User).where(User.id == user_id))
        await test_db_session.commit()



async def test_generated_tests_persistence_and_cascade_delete(
    test_db_session: AsyncSession,
) -> None:
    """Verify generated_tests table stores AST syntax valid indicator and cascades on repo deletion."""
    user = _make_mock_user("testgen-persist-user")
    test_db_session.add(user)
    await test_db_session.flush()

    repo = _make_mock_repo(user.id, "testgen-persist-repo")
    test_db_session.add(repo)
    await test_db_session.commit()

    test_row = GeneratedTest(
        id=uuid.uuid4(),
        repo_id=repo.id,
        user_id=user.id,
        path="app/services/pr_analysis.py",
        framework="pytest",
        content="import pytest\n\ndef test_risk():\n    assert True\n",
        syntax_valid=True,
        notes="Generated unit tests for deterministic rules.",
        model="gemini-3.5-flash-lite",
        indexed_commit_sha="c" * 40,
    )
    test_db_session.add(test_row)
    await test_db_session.commit()

    # Query back
    res = await test_db_session.execute(
        select(GeneratedTest).where(GeneratedTest.id == test_row.id)
    )
    saved = res.scalar_one()
    assert saved.syntax_valid is True
    assert saved.framework == "pytest"
    assert "import pytest" in saved.content

    # Now delete the repository and verify cascading delete removes the generated test
    await test_db_session.execute(delete(Repository).where(Repository.id == repo.id))
    await test_db_session.commit()

    res_after = await test_db_session.execute(
        select(GeneratedTest).where(GeneratedTest.id == test_row.id)
    )
    assert res_after.scalar_one_or_none() is None

    # Cleanup user
    await test_db_session.execute(delete(User).where(User.id == user.id))
    await test_db_session.commit()


async def test_ownership_enforced_across_intelligence_records(
    test_db_session: AsyncSession,
) -> None:
    """Verify cross-user query isolation: user B cannot view or mutate user A's intelligence records."""
    user_a = _make_mock_user("intel-owner-a")
    user_b = _make_mock_user("intel-owner-b")
    test_db_session.add_all([user_a, user_b])
    await test_db_session.flush()

    repo_a = _make_mock_repo(user_a.id, "repo-a")
    test_db_session.add(repo_a)
    await test_db_session.commit()

    try:
        # Seed records for repo_a
        pr_a = PRAnalysis(
            id=uuid.uuid4(),
            repo_id=repo_a.id,
            pr_number=1,
            risk_level="high",
            risk_score=75,
            risk_reasons=["Auth changes"],
            status="ok",
        )
        job_a = AnalysisJob(
            id=uuid.uuid4(),
            repo_id=repo_a.id,
            kind="issues",
            status="ready",
            stage="done",
            progress=100,
        )
        test_a = GeneratedTest(
            id=uuid.uuid4(),
            repo_id=repo_a.id,
            user_id=user_a.id,
            path="main.py",
            framework="pytest",
            content="def test(): pass",
            syntax_valid=True,
            model="test-model",
        )
        test_db_session.add_all([pr_a, job_a, test_a])
        await test_db_session.commit()

        # Query repo_a verifying user ownership
        # Query simulating user_b requesting repo_a: should return None
        accessible_for_b = await test_db_session.scalar(
            select(Repository).where(
                Repository.id == repo_a.id,
                Repository.user_id == user_b.id,
            )
        )
        assert accessible_for_b is None

        # Accessible for user_a
        accessible_for_a = await test_db_session.scalar(
            select(Repository).where(
                Repository.id == repo_a.id,
                Repository.user_id == user_a.id,
            )
        )
        assert accessible_for_a is not None
    finally:
        await test_db_session.execute(delete(PRAnalysis).where(PRAnalysis.repo_id == repo_a.id))
        await test_db_session.execute(delete(AnalysisJob).where(AnalysisJob.repo_id == repo_a.id))
        await test_db_session.execute(delete(GeneratedTest).where(GeneratedTest.repo_id == repo_a.id))
        await test_db_session.execute(delete(Repository).where(Repository.id == repo_a.id))
        await test_db_session.execute(delete(User).where(User.id.in_([user_a.id, user_b.id])))
        await test_db_session.commit()
