"""In-memory database session and seed provider for standalone Demo Mode without Docker/PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.security import encrypt_token
from app.models.code_chunk import CodeChunk
from app.models.commit import Commit
from app.models.index_job import IndexJob
from app.models.issue import Issue
from app.models.pull_request import PullRequest
from app.models.qa_history import QAHistory
from app.models.repo_doc import RepoDoc
from app.models.repo_file import RepoFile
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User

DEMO_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEMO_REPO_1_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEMO_REPO_2_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


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

    def all(self) -> list[Any]:
        return self._items


class DemoInMemorySession:
    """In-memory async database session simulating PostgreSQL for standalone demo execution."""

    def __init__(self) -> None:
        self.users_by_id: dict[uuid.UUID, User] = {}
        self.users_by_github_id: dict[int, User] = {}
        self.repos_by_id: dict[uuid.UUID, Repository] = {}
        self.sync_jobs_by_id: dict[uuid.UUID, SyncJob] = {}
        self.index_jobs_by_id: dict[uuid.UUID, IndexJob] = {}
        self.repo_files_by_id: dict[uuid.UUID, RepoFile] = {}
        self.code_chunks_by_id: dict[uuid.UUID, CodeChunk] = {}
        self.commits_by_id: dict[uuid.UUID, Commit] = {}
        self.pulls_by_id: dict[uuid.UUID, PullRequest] = {}
        self.issues_by_id: dict[uuid.UUID, Issue] = {}
        self.qa_history_by_id: dict[uuid.UUID, QAHistory] = {}
        self.repo_docs_by_id: dict[uuid.UUID, RepoDoc] = {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []

    async def get(self, entity_cls: Any, ident: Any) -> Any:
        if isinstance(ident, str):
            try:
                ident = uuid.UUID(ident)
            except ValueError:
                pass
        if entity_cls is Repository:
            return self.repos_by_id.get(ident)
        if entity_cls is User:
            return self.users_by_id.get(ident)
        if entity_cls is IndexJob:
            return self.index_jobs_by_id.get(ident)
        if entity_cls is SyncJob:
            return self.sync_jobs_by_id.get(ident)
        if entity_cls is RepoFile:
            return self.repo_files_by_id.get(ident)
        if entity_cls is CodeChunk:
            return self.code_chunks_by_id.get(ident)
        if entity_cls is QAHistory:
            return self.qa_history_by_id.get(ident)
        if entity_cls is RepoDoc:
            return self.repo_docs_by_id.get(ident)
        return None

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> FakeScalarResult:
        stmt_str = str(statement)

        # Health check query: SELECT 1
        if stmt_str.strip().startswith("SELECT 1") or stmt_str.strip() == "SELECT 1":
            return FakeScalarResult(1)

        # Bound parameters
        params: dict[str, Any] = {}
        if hasattr(statement, "compile"):
            try:
                compiled = statement.compile()
                params = getattr(compiled, "params", {}) or {}
            except Exception:
                pass

        # Handle INSERT INTO commits / pull_requests / issues
        if "INSERT INTO" in stmt_str:
            if "commits" in stmt_str:
                repo_id = params.get("repo_id")
                sha = params.get("sha")
                existing = next(
                    (c for c in self.commits_by_id.values() if c.repo_id == repo_id and c.sha == sha),
                    None,
                )
                if existing:
                    existing.author_login = params.get("author_login", existing.author_login)
                    existing.author_name = params.get("author_name", existing.author_name)
                    existing.message = params.get("message", existing.message)
                    existing.committed_at = params.get("committed_at", existing.committed_at)
                    existing.additions = params.get("additions", existing.additions)
                    existing.deletions = params.get("deletions", existing.deletions)
                    existing.files_changed = params.get("files_changed", existing.files_changed)
                else:
                    new_commit = Commit(
                        id=uuid.uuid4(),
                        repo_id=repo_id,
                        sha=sha,
                        author_login=params.get("author_login"),
                        author_name=params.get("author_name"),
                        message=params.get("message", ""),
                        committed_at=params.get("committed_at", datetime.now(UTC)),
                        additions=params.get("additions"),
                        deletions=params.get("deletions"),
                        files_changed=params.get("files_changed"),
                    )
                    self.add(new_commit)
                return FakeScalarResult(None)

            if "pull_requests" in stmt_str:
                repo_id = params.get("repo_id")
                number = params.get("number")
                existing = next(
                    (p for p in self.pulls_by_id.values() if p.repo_id == repo_id and p.number == number),
                    None,
                )
                if existing:
                    existing.title = params.get("title", existing.title)
                    existing.body = params.get("body", existing.body)
                    existing.state = params.get("state", existing.state)
                    existing.author_login = params.get("author_login", existing.author_login)
                    existing.merged_at = params.get("merged_at", existing.merged_at)
                    existing.closed_at = params.get("closed_at", existing.closed_at)
                    existing.additions = params.get("additions", existing.additions)
                    existing.deletions = params.get("deletions", existing.deletions)
                    existing.changed_files = params.get("changed_files", existing.changed_files)
                    existing.base_ref = params.get("base_ref", existing.base_ref)
                    existing.head_ref = params.get("head_ref", existing.head_ref)
                else:
                    new_pr = PullRequest(
                        id=uuid.uuid4(),
                        repo_id=repo_id,
                        number=number,
                        title=params.get("title", ""),
                        body=params.get("body"),
                        state=params.get("state", "open"),
                        author_login=params.get("author_login"),
                        created_at=params.get("created_at", datetime.now(UTC)),
                        merged_at=params.get("merged_at"),
                        closed_at=params.get("closed_at"),
                        additions=params.get("additions"),
                        deletions=params.get("deletions"),
                        changed_files=params.get("changed_files"),
                        base_ref=params.get("base_ref"),
                        head_ref=params.get("head_ref"),
                    )
                    self.add(new_pr)
                return FakeScalarResult(None)

            if "issues" in stmt_str:
                repo_id = params.get("repo_id")
                number = params.get("number")
                existing = next(
                    (i for i in self.issues_by_id.values() if i.repo_id == repo_id and i.number == number),
                    None,
                )
                if existing:
                    existing.title = params.get("title", existing.title)
                    existing.body = params.get("body", existing.body)
                    existing.state = params.get("state", existing.state)
                    existing.labels = params.get("labels", existing.labels)
                    existing.author_login = params.get("author_login", existing.author_login)
                    existing.closed_at = params.get("closed_at", existing.closed_at)
                else:
                    new_issue = Issue(
                        id=uuid.uuid4(),
                        repo_id=repo_id,
                        number=number,
                        title=params.get("title", ""),
                        body=params.get("body"),
                        state=params.get("state", "open"),
                        labels=params.get("labels", []),
                        author_login=params.get("author_login"),
                        created_at=params.get("created_at", datetime.now(UTC)),
                        closed_at=params.get("closed_at"),
                    )
                    self.add(new_issue)
                return FakeScalarResult(None)

        # Repositories queries
        if "repositories" in stmt_str:
            if "repositories.github_id" in stmt_str and "SELECT repositories.github_id" in stmt_str:
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
            matched.sort(key=lambda r: r.created_at, reverse=True)
            return FakeScalarResult(matched[0] if matched else None, items=matched)

        # SyncJobs queries
        if "sync_jobs" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_jobs = [
                j for j in self.sync_jobs_by_id.values()
                if repo_id is None or j.repo_id == repo_id
            ]
            matched_jobs.sort(key=lambda j: j.created_at, reverse=True)
            return FakeScalarResult(matched_jobs[0] if matched_jobs else None, items=matched_jobs)

        # Commits queries
        if "commits" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_commits = [
                c for c in self.commits_by_id.values()
                if repo_id is None or c.repo_id == repo_id
            ]
            for v in params.values():
                if isinstance(v, str) and v.startswith("%") and v.endswith("%"):
                    sub = v.strip("%").lower()
                    matched_commits = [
                        c for c in matched_commits
                        if (c.author_login and sub in c.author_login.lower())
                        or (c.author_name and sub in c.author_name.lower())
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
            for v in params.values():
                if v in ("open", "closed"):
                    matched_prs = [p for p in matched_prs if p.state == v]
                elif isinstance(v, str) and v.startswith("%") and v.endswith("%"):
                    sub = v.strip("%").lower()
                    matched_prs = [p for p in matched_prs if p.author_login and sub in p.author_login.lower()]
            matched_prs.sort(key=lambda p: p.created_at, reverse=True)
            return FakeScalarResult(matched_prs[0] if matched_prs else None, items=matched_prs)

        # Issues queries
        if "issues" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_issues = [
                i for i in self.issues_by_id.values()
                if repo_id is None or i.repo_id == repo_id
            ]
            for v in params.values():
                if v in ("open", "closed"):
                    matched_issues = [i for i in matched_issues if i.state == v]
                elif isinstance(v, str) and v.startswith("%") and v.endswith("%"):
                    sub = v.strip("%").lower()
                    matched_issues = [i for i in matched_issues if i.author_login and sub in i.author_login.lower()]
            matched_issues.sort(key=lambda i: i.created_at, reverse=True)
            return FakeScalarResult(matched_issues[0] if matched_issues else None, items=matched_issues)

        # IndexJobs queries
        if "index_jobs" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_jobs = [
                j for j in self.index_jobs_by_id.values()
                if repo_id is None or j.repo_id == repo_id
            ]
            matched_jobs.sort(key=lambda j: j.created_at, reverse=True)
            return FakeScalarResult(matched_jobs[0] if matched_jobs else None, items=matched_jobs)

        # CodeChunks queries
        if "code_chunks" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_chunks = [
                c for c in self.code_chunks_by_id.values()
                if repo_id is None or c.repo_id == repo_id
            ]
            if "cosine_distance" in stmt_str or "distance" in stmt_str:
                dist_items = [(c, 0.1) for c in matched_chunks]
                return FakeScalarResult(dist_items[0] if dist_items else None, items=dist_items)
            if "ts_rank" in stmt_str or "rank" in stmt_str:
                rank_items = [(c, 0.9) for c in matched_chunks]
                return FakeScalarResult(rank_items[0] if rank_items else None, items=rank_items)
            return FakeScalarResult(matched_chunks[0] if matched_chunks else None, items=matched_chunks)

        # RepoFiles queries
        if "repo_files" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            matched_files = [
                f for f in self.repo_files_by_id.values()
                if repo_id is None or f.repo_id == repo_id
            ]
            if stmt_str.strip().startswith("SELECT repo_files.path"):
                paths = [f.path for f in matched_files]
                return FakeScalarResult(paths[0] if paths else None, items=paths)
            return FakeScalarResult(matched_files[0] if matched_files else None, items=matched_files)

        # QAHistory queries
        if "qa_history" in stmt_str:
            hist_id = next((v for v in params.values() if isinstance(v, uuid.UUID) and v in self.qa_history_by_id), None)
            if hist_id:
                h = self.qa_history_by_id.get(hist_id)
                return FakeScalarResult(h, items=[h] if h else [])
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID) and v in self.repos_by_id), None)
            matched_hists = [
                h for h in self.qa_history_by_id.values()
                if repo_id is None or h.repo_id == repo_id
            ]
            matched_hists.sort(key=lambda h: h.created_at, reverse=True)
            return FakeScalarResult(matched_hists[0] if matched_hists else None, items=matched_hists)

        # RepoDocs queries
        if "repo_docs" in stmt_str:
            repo_id = next((v for v in params.values() if isinstance(v, uuid.UUID)), None)
            doc_type = next((v for v in params.values() if isinstance(v, str) and v in ("architecture", "readme")), None)
            matched_docs = [
                d for d in self.repo_docs_by_id.values()
                if (repo_id is None or d.repo_id == repo_id)
                and (doc_type is None or d.doc_type == doc_type)
            ]
            doc = matched_docs[0] if matched_docs else None
            return FakeScalarResult(doc, items=matched_docs)

        # User queries
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
            if not getattr(instance, "default_branch", None):
                instance.default_branch = "main"
            if getattr(instance, "is_private", None) is None:
                instance.is_private = False
            self.repos_by_id[instance.id] = instance
        elif isinstance(instance, SyncJob):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.sync_jobs_by_id[instance.id] = instance
        elif isinstance(instance, IndexJob):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.index_jobs_by_id[instance.id] = instance
        elif isinstance(instance, CodeChunk):
            if not instance.id:
                instance.id = uuid.uuid4()
            self.code_chunks_by_id[instance.id] = instance
        elif isinstance(instance, QAHistory):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            self.qa_history_by_id[instance.id] = instance
        elif isinstance(instance, RepoDoc):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not instance.created_at:
                instance.created_at = now
            if not instance.updated_at:
                instance.updated_at = now
            self.repo_docs_by_id[instance.id] = instance
        elif isinstance(instance, RepoFile):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not getattr(instance, "indexed_at", None):
                instance.indexed_at = now
            self.repo_files_by_id[instance.id] = instance
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
            if not getattr(instance, "created_at", None):
                instance.created_at = now
            if not getattr(instance, "updated_at", None):
                instance.updated_at = now
            self.pulls_by_id[instance.id] = instance
        elif isinstance(instance, Issue):
            if not instance.id:
                instance.id = uuid.uuid4()
            if not getattr(instance, "created_at", None):
                instance.created_at = now
            if not getattr(instance, "updated_at", None):
                instance.updated_at = now
            self.issues_by_id[instance.id] = instance

        self.added.append(instance)

    async def delete(self, instance: Any) -> None:
        if isinstance(instance, Repository) and instance.id in self.repos_by_id:
            del self.repos_by_id[instance.id]
            # Also cascade delete commits, PRs, issues, sync jobs, index jobs, chunks, files
            self.commits_by_id = {k: v for k, v in self.commits_by_id.items() if v.repo_id != instance.id}
            self.pulls_by_id = {k: v for k, v in self.pulls_by_id.items() if v.repo_id != instance.id}
            self.issues_by_id = {k: v for k, v in self.issues_by_id.items() if v.repo_id != instance.id}
            self.sync_jobs_by_id = {k: v for k, v in self.sync_jobs_by_id.items() if v.repo_id != instance.id}
            self.index_jobs_by_id = {k: v for k, v in self.index_jobs_by_id.items() if v.repo_id != instance.id}
            self.code_chunks_by_id = {k: v for k, v in self.code_chunks_by_id.items() if v.repo_id != instance.id}
            self.repo_files_by_id = {k: v for k, v in self.repo_files_by_id.items() if v.repo_id != instance.id}
        elif isinstance(instance, User) and instance.id in self.users_by_id:
            del self.users_by_id[instance.id]
        elif isinstance(instance, QAHistory) and instance.id in self.qa_history_by_id:
            del self.qa_history_by_id[instance.id]
        elif isinstance(instance, RepoDoc) and instance.id in self.repo_docs_by_id:
            del self.repo_docs_by_id[instance.id]

        self.deleted.append(instance)

    async def refresh(self, instance: Any) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass


class FakeRedis:
    """Mock Redis client for standalone execution."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> Any:
        return self._data.get(key)

    async def set(self, key: str, val: Any, *args: Any, **kwargs: Any) -> bool:
        self._data[key] = val
        return True

    async def incr(self, key: str) -> int:
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = val
        return val

    async def expire(self, key: str, seconds: int) -> bool:
        return True


# Global shared demo store instance
_demo_session_instance: DemoInMemorySession | None = None
_demo_redis_instance = FakeRedis()


def get_demo_session() -> DemoInMemorySession:
    """Return the singleton in-memory session populated with rich demo data."""
    global _demo_session_instance
    if _demo_session_instance is None:
        _demo_session_instance = DemoInMemorySession()
        seed_demo_data(_demo_session_instance)
    return _demo_session_instance


def seed_demo_data(db: DemoInMemorySession) -> None:
    """Seed the database with realistic demo user, repos, commits, PRs, and issues."""
    now = datetime.now(UTC)

    # 1. Demo User
    demo_user = User(
        id=DEMO_USER_ID,
        github_id=8923011,
        login="avanthikasreejith8923-a11y",
        name="Avanthika Sreejith",
        avatar_url="https://avatars.githubusercontent.com/u/8923011?v=4",
        email="avanthika@developer.local",
        encrypted_access_token=encrypt_token("ghp_demo_mock_token_for_local_display"),
    )
    db.add(demo_user)

    # 2. Main Demo Repository: repo-cartographer
    repo1 = Repository(
        id=DEMO_REPO_1_ID,
        user_id=DEMO_USER_ID,
        github_id=89230101,
        full_name="avanthikasreejith8923-a11y/repo-cartographer",
        description="AI Developer Productivity Platform: Codebase Graphing, Ingestion, and RAG with Citations",
        default_branch="main",
        language="TypeScript",
        is_private=False,
        status="ready",
        index_status="ready",
        indexed_commit_sha="7ff268f9e58280471bd27b465dbacd7666a24864",
        chunk_count=184,
        last_synced_at=now - timedelta(minutes=15),
    )
    db.add(repo1)

    # Sync job for repo1
    job1 = SyncJob(
        id=uuid.uuid4(),
        repo_id=DEMO_REPO_1_ID,
        status="completed",
        stage="completed",
        progress=100,
        started_at=now - timedelta(minutes=16),
        finished_at=now - timedelta(minutes=15),
    )
    db.add(job1)

    # Commits for repo1
    sample_commits = [
        ("7ff268f9e58280471bd27b465dbacd7666a24864", "docs: add sync pipeline tests, update README and ARCHITECTURE, tick Phase 2", "avanthika", "Avanthika Sreejith", 142, 18, 5, 1),
        ("3ef93911adbe90065b77893c29b3d9b476520fe0", "feat: add frontend import page, repo list with status, and repo detail tabs", "avanthika", "Avanthika Sreejith", 380, 25, 6, 2),
        ("7067a2e8546a33e2455fc6ac7e580a9b2ac38281", "feat: add sync trigger/status endpoints and commits, pulls, issues listing", "avanthika", "Avanthika Sreejith", 210, 12, 4, 3),
        ("e381f8cd71dbbacea528928c034c317c9e5de865", "feat: add issue ingestion to sync job (excluding pull requests)", "avanthika", "Avanthika Sreejith", 125, 8, 3, 4),
        ("e504117b11324dc88eaef39ff92705a0a57990d5", "feat: add pull request ingestion to sync job with branch refs", "avanthika", "Avanthika Sreejith", 195, 15, 3, 5),
        ("7a993a78c045699a3c06e387b5cf159a5461156d", "feat: add idempotent commit ingestion to sync job (ON CONFLICT DO UPDATE)", "avanthika", "Avanthika Sreejith", 160, 10, 2, 6),
        ("419c99c7e05494a83409bd4a84f4767889890c94", "feat: add sync job for repository metadata with status tracking", "avanthika", "Avanthika Sreejith", 110, 5, 2, 7),
        ("abd529da7205e8ca9de72548242c2b888935ce08", "build: add ARQ worker setup and worker service to docker-compose", "avanthika", "Avanthika Sreejith", 85, 2, 2, 8),
        ("d4c6fbc834b9ea29af971b39f6722e82c4f00448", "feat: add repos list, detail, and delete endpoints with ownership checks", "avanthika", "Avanthika Sreejith", 175, 20, 3, 9),
        ("f2159e51241198571bd27b465dbacd7666a24864", "test: add GitHub client tests for pagination, rate limits, and retries", "avanthika", "Avanthika Sreejith", 220, 5, 2, 10),
    ]

    for sha, msg, login, name, adds, dels, files, hours_ago in sample_commits:
        c = Commit(
            id=uuid.uuid4(),
            repo_id=DEMO_REPO_1_ID,
            sha=sha,
            message=msg,
            author_login=login,
            author_name=name,
            committed_at=now - timedelta(hours=hours_ago * 4),
            additions=adds,
            deletions=dels,
            files_changed=files,
        )
        db.add(c)

    # RepoFiles & CodeChunks for repo1 (Phase 3 & Phase 4 Code Intelligence)
    demo_files = [
        ("backend/app/main.py", "FastAPI application entry point, lifecycle events, and route inclusion.\napp = FastAPI(title='Repo Cartographer', version='0.1.0')", "python", "app"),
        ("backend/app/core/config.py", "class Settings(BaseSettings):\n    PROJECT_NAME: str = 'Repo Cartographer'\n    LLM_PROVIDER: str = 'gemini'\n    LLM_MODEL: str = 'gemini-3.5-flash-lite'", "python", "Settings"),
        ("backend/app/services/qa.py", "async def ask_codebase(repo, user, question):\n    # Grounded codebase question answering with citation validation [S1]", "python", "ask_codebase"),
        ("README.md", "# Repo Cartographer\nAI Developer Productivity Platform with pgvector hybrid search, grounded Q&A, and documentation generation.", "markdown", "README"),
    ]
    for path, content, lang, sym in demo_files:
        rf = RepoFile(
            id=uuid.uuid4(),
            repo_id=DEMO_REPO_1_ID,
            path=path,
            size_bytes=len(content),
            content_hash=f"hash_{path}",
        )
        db.add(rf)
        chunk = CodeChunk(
            id=uuid.uuid4(),
            repo_id=DEMO_REPO_1_ID,
            file_id=rf.id,
            path=path,
            chunk_index=0,
            start_line=1,
            end_line=30,
            content=content,
            content_hash=f"chunk_hash_{path}",
            symbol=sym,
            language=lang,
            kind="definition" if sym != "README" else "document",
            embedding=[0.01] * 768,
            embedding_model="text-embedding-004",
        )
        db.add(chunk)

    # Pull Requests for repo1
    sample_prs = [
        (6, "feat: Phase 3 AST parsing & symbol relationship extraction", "open", "avanthika", "feature/ast-parsing", "main", 420, 35, 12, 1),
        (5, "feat: asynchronous ingestion pipeline & ARQ worker queue", "merged", "avanthika", "feat/ingestion-pipeline", "main", 540, 48, 8, 24),
        (4, "feat: GitHub OAuth 2.0 Web Application Flow & Fernet Encryption", "merged", "avanthika", "feat/auth-flow", "main", 390, 22, 6, 48),
        (3, "refactor: FastAPI async database dependency injection & session management", "closed", "contributor", "refactor/db-deps", "main", 110, 95, 4, 72),
    ]
    for num, title, state, login, head, base, adds, dels, files, hours_ago in sample_prs:
        pr = PullRequest(
            id=uuid.uuid4(),
            repo_id=DEMO_REPO_1_ID,
            number=num,
            title=title,
            body=f"Implements {title.lower()} according to the repo-cartographer technical specification.",
            state=state,
            author_login=login,
            head_ref=head,
            base_ref=base,
            additions=adds,
            deletions=dels,
            changed_files=files,
            created_at=now - timedelta(hours=hours_ago),
            merged_at=now - timedelta(hours=hours_ago - 2) if state == "merged" else None,
            closed_at=now - timedelta(hours=hours_ago - 1) if state in ("closed", "merged") else None,
        )
        db.add(pr)

    # Issues for repo1
    sample_issues = [
        (14, "Implement Python and TypeScript AST extractors (Phase 3)", "open", [{"name": "phase-3", "color": "6366f1"}, {"name": "enhancement", "color": "10b981"}], "avanthika", 6),
        (13, "Add vector index with pgvector HNSW for source code embeddings (Phase 4)", "open", [{"name": "phase-4", "color": "8b5cf6"}, {"name": "architecture", "color": "3b82f6"}], "avanthika", 18),
        (12, "Configure setup-python cache-dependency-path for monorepo CI", "closed", [{"name": "bug", "color": "ef4444"}, {"name": "ci", "color": "f59e0b"}], "avanthika", 26),
        (11, "Ensure rate limit backoff uses secondary retry-after headers", "closed", [{"name": "bug", "color": "ef4444"}], "avanthika", 48),
        (10, "Design hybrid graph + vector search retrieval pipeline (Phase 5)", "open", [{"name": "phase-5", "color": "ec4899"}, {"name": "research", "color": "64748b"}], "avanthika", 60),
    ]
    for num, title, state, labels, login, hours_ago in sample_issues:
        issue = Issue(
            id=uuid.uuid4(),
            repo_id=DEMO_REPO_1_ID,
            number=num,
            title=title,
            body=f"Tracking issue for: {title}",
            state=state,
            labels=labels,
            author_login=login,
            created_at=now - timedelta(hours=hours_ago),
            closed_at=now - timedelta(hours=hours_ago - 8) if state == "closed" else None,
        )
        db.add(issue)

    # 3. Secondary Demo Repository: fastapi/fastapi
    repo2 = Repository(
        id=DEMO_REPO_2_ID,
        user_id=DEMO_USER_ID,
        github_id=89230102,
        full_name="fastapi/fastapi",
        description="FastAPI framework, high performance, easy to learn, fast to code, ready for production",
        default_branch="master",
        language="Python",
        is_private=False,
        status="ready",
        last_synced_at=now - timedelta(hours=2),
    )
    db.add(repo2)

    job2 = SyncJob(
        id=uuid.uuid4(),
        repo_id=DEMO_REPO_2_ID,
        status="completed",
        stage="completed",
        progress=100,
        started_at=now - timedelta(hours=2, minutes=2),
        finished_at=now - timedelta(hours=2),
    )
    db.add(job2)

    c_fastapi = Commit(
        id=uuid.uuid4(),
        repo_id=DEMO_REPO_2_ID,
        sha="99887766554433221100aabbccddeeff00112233",
        message="feat: support modern typing annotations and async lifespan hooks",
        author_login="tiangolo",
        author_name="Sebastián Ramírez",
        committed_at=now - timedelta(days=1),
        additions=95,
        deletions=12,
        files_changed=3,
    )
    db.add(c_fastapi)
