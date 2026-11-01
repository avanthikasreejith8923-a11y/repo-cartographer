"""Tests for repository discovery and import API endpoints."""

import uuid

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token
from app.models.repository import Repository
from app.models.user import User
from tests.conftest import InMemoryAsyncSession


def create_authenticated_user(fake_db: InMemoryAsyncSession) -> tuple[User, dict[str, str]]:
    """Helper to persist a test user and generate session cookies."""
    user = User(
        id=uuid.uuid4(),
        github_id=999888,
        login="testuser",
        name="Test User",
        encrypted_access_token=encrypt_token("ghp_testaccesstoken"),
    )
    fake_db.add(user)
    token = create_session_token({"sub": str(user.id)})
    cookies = {settings.SESSION_COOKIE_NAME: token}
    return user, cookies


@pytest.mark.asyncio
async def test_list_available_repos_unauthenticated_returns_401(client: httpx.AsyncClient):
    """GET /repos/available without session cookie returns 401 Unauthorized."""
    response = await client.get("/repos/available")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_available_repos_authenticated(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/available flags already imported repos correctly."""
    user, cookies = create_authenticated_user(fake_db)

    # Pre-import repo 101
    imported_repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=101,
        full_name="testuser/repo-imported",
        status="ready",
    )
    fake_db.add(imported_repo)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/user/repos").respond(
            status_code=200,
            json=[
                {"id": 101, "name": "repo-imported", "full_name": "testuser/repo-imported", "private": False},
                {"id": 102, "name": "repo-new", "full_name": "testuser/repo-new", "private": True},
            ],
        )

        response = await client.get("/repos/available", cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        by_id = {r["github_id"]: r for r in data}
        assert by_id[101]["is_imported"] is True
        assert by_id[102]["is_imported"] is False


@pytest.mark.asyncio
async def test_import_repository_unauthenticated_returns_401(client: httpx.AsyncClient):
    """POST /repos/import without session cookie returns 401."""
    response = await client.post("/repos/import", json={"full_name": "octocat/Hello-World"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_import_repository_success(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/import successfully creates repository and sync job."""
    _, cookies = create_authenticated_user(fake_db)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World").respond(
            status_code=200,
            json={
                "id": 1296269,
                "name": "Hello-World",
                "full_name": "octocat/Hello-World",
                "description": "My first repository",
                "private": False,
                "default_branch": "master",
                "language": "C",
            },
        )

        response = await client.post(
            "/repos/import",
            json={"full_name": "octocat/Hello-World"},
            cookies=cookies,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["repository"]["full_name"] == "octocat/Hello-World"
        assert data["repository"]["status"] == "pending"
        assert data["sync_job"]["status"] == "pending"
        assert data["sync_job"]["stage"] == "queued"
        assert len(fake_db.repos_by_id) == 1


@pytest.mark.asyncio
async def test_import_repository_already_imported_returns_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/import for an existing repo returns 409 Conflict."""
    user, cookies = create_authenticated_user(fake_db)

    existing_repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=1296269,
        full_name="octocat/Hello-World",
        status="ready",
    )
    fake_db.add(existing_repo)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World").respond(
            status_code=200,
            json={
                "id": 1296269,
                "name": "Hello-World",
                "full_name": "octocat/Hello-World",
            },
        )

        response = await client.post(
            "/repos/import",
            json={"full_name": "octocat/Hello-World"},
            cookies=cookies,
        )
        assert response.status_code == 409
        assert "already imported" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_repository_not_found_on_github_returns_404(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/import returns 404 if repository does not exist on GitHub."""
    _, cookies = create_authenticated_user(fake_db)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/nonexistent/repo").respond(
            status_code=404,
            json={"message": "Not Found"},
        )

        response = await client.post(
            "/repos/import",
            json={"full_name": "nonexistent/repo"},
            cookies=cookies,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_repositories_returns_only_user_repos(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos returns only repos owned by current user."""
    user1, cookies1 = create_authenticated_user(fake_db)
    user2_id = uuid.uuid4()

    # User 1 repo
    repo1 = Repository(
        id=uuid.uuid4(),
        user_id=user1.id,
        github_id=201,
        full_name="user1/repo1",
        status="ready",
    )
    fake_db.add(repo1)

    # User 2 repo
    repo2 = Repository(
        id=uuid.uuid4(),
        user_id=user2_id,
        github_id=202,
        full_name="user2/repo2",
        status="ready",
    )
    fake_db.add(repo2)

    response = await client.get("/repos", cookies=cookies1)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "user1/repo1"


@pytest.mark.asyncio
async def test_get_repository_success_and_ownership(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id} returns repo if owned, and 404 if owned by another user."""
    user1, cookies1 = create_authenticated_user(fake_db)
    user2_id = uuid.uuid4()

    repo1 = Repository(
        id=uuid.uuid4(),
        user_id=user1.id,
        github_id=301,
        full_name="user1/repo1",
        status="ready",
    )
    fake_db.add(repo1)

    repo_other = Repository(
        id=uuid.uuid4(),
        user_id=user2_id,
        github_id=302,
        full_name="user2/private-repo",
        status="ready",
    )
    fake_db.add(repo_other)

    # Own repo -> 200
    resp_own = await client.get(f"/repos/{repo1.id}", cookies=cookies1)
    assert resp_own.status_code == 200
    assert resp_own.json()["id"] == str(repo1.id)

    # Other user's repo -> 404
    resp_other = await client.get(f"/repos/{repo_other.id}", cookies=cookies1)
    assert resp_other.status_code == 404

    # Nonexistent repo -> 404
    resp_none = await client.get(f"/repos/{uuid.uuid4()}", cookies=cookies1)
    assert resp_none.status_code == 404


@pytest.mark.asyncio
async def test_delete_repository_success_and_ownership(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """DELETE /repos/{id} deletes own repo and returns 404 for other user's repo."""
    user1, cookies1 = create_authenticated_user(fake_db)
    user2_id = uuid.uuid4()

    repo1 = Repository(
        id=uuid.uuid4(),
        user_id=user1.id,
        github_id=401,
        full_name="user1/repo-to-delete",
        status="ready",
    )
    fake_db.add(repo1)

    repo_other = Repository(
        id=uuid.uuid4(),
        user_id=user2_id,
        github_id=402,
        full_name="user2/repo-do-not-delete",
        status="ready",
    )
    fake_db.add(repo_other)

    # Attempt delete other user's repo -> 404
    resp_other = await client.delete(f"/repos/{repo_other.id}", cookies=cookies1)
    assert resp_other.status_code == 404
    assert repo_other.id in fake_db.repos_by_id

    # Delete own repo -> 204
    resp_own = await client.delete(f"/repos/{repo1.id}", cookies=cookies1)
    assert resp_own.status_code == 204
    assert repo1.id not in fake_db.repos_by_id


@pytest.mark.asyncio
async def test_trigger_sync_and_get_sync_status(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/sync triggers a re-sync and GET /repos/{id}/sync-status returns progress."""
    user, cookies = create_authenticated_user(fake_db)

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=501,
        full_name="testuser/resync-repo",
        status="ready",
    )
    fake_db.add(repo)

    # 1. Trigger sync
    resp_sync = await client.post(f"/repos/{repo.id}/sync", cookies=cookies)
    assert resp_sync.status_code == 202
    sync_data = resp_sync.json()
    assert sync_data["status"] == "pending"
    assert sync_data["stage"] == "queued"
    assert sync_data["progress"] == 0
    assert repo.status == "pending"

    # 1b. Duplicate sync while already pending returns 409 Conflict
    resp_sync_conflict = await client.post(f"/repos/{repo.id}/sync", cookies=cookies)
    assert resp_sync_conflict.status_code == 409
    assert resp_sync_conflict.json()["detail"] == "Repository synchronization is already pending or running"

    # 2. Get sync status
    resp_status = await client.get(f"/repos/{repo.id}/sync-status", cookies=cookies)
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["id"] == sync_data["id"]
    assert status_data["stage"] == "queued"

    # 3. Another user accessing this repo returns 404
    _, other_cookies = create_authenticated_user(fake_db)
    resp_unauth = await client.get(f"/repos/{repo.id}/sync-status", cookies=other_cookies)
    assert resp_unauth.status_code == 404


@pytest.mark.asyncio
async def test_trigger_sync_and_index_already_active_returns_409(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """POST /repos/{id}/sync and POST /repos/{id}/index return 409 if a job is already running or pending."""
    from app.models.index_job import IndexJob

    user, cookies = create_authenticated_user(fake_db)

    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=9988,
        full_name="testuser/active-job-repo",
        status="syncing",
        index_status="ready",
    )
    fake_db.add(repo)

    # If repo status was syncing but there is NO active job, POST /sync is accepted (resets/reconciles)
    res_sync_accepted = await client.post(f"/repos/{repo.id}/sync", cookies=cookies)
    assert res_sync_accepted.status_code == 202

    # Now that an active SyncJob is running, a second POST /sync returns 409 Conflict
    res_sync_409 = await client.post(f"/repos/{repo.id}/sync", cookies=cookies)
    assert res_sync_409.status_code == 409

    # Add an active running IndexJob -> POST /index returns 409 even if repo.index_status is ready
    active_idx_job = IndexJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="running",
        stage="chunking",
        progress=50,
    )
    fake_db.add(active_idx_job)

    res_idx_409 = await client.post(f"/repos/{repo.id}/index", cookies=cookies)
    assert res_idx_409.status_code == 409


@pytest.mark.asyncio
async def test_list_repo_commits(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/commits retrieves commits with author filtering."""
    from datetime import UTC, datetime

    from app.models.commit import Commit

    user, cookies = create_authenticated_user(fake_db)
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=601,
        full_name="testuser/commits-repo",
        status="ready",
    )
    fake_db.add(repo)

    c1 = Commit(
        id=uuid.uuid4(),
        repo_id=repo.id,
        sha="1111111111111111111111111111111111111111",
        author_login="alice",
        author_name="Alice A",
        message="feat: first commit",
        committed_at=datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC),
        additions=10,
        deletions=2,
        files_changed=1,
    )
    c2 = Commit(
        id=uuid.uuid4(),
        repo_id=repo.id,
        sha="2222222222222222222222222222222222222222",
        author_login="bob",
        author_name="Bob B",
        message="fix: bugfix commit",
        committed_at=datetime(2026, 10, 2, 11, 0, 0, tzinfo=UTC),
        additions=5,
        deletions=1,
        files_changed=1,
    )
    fake_db.add(c1)
    fake_db.add(c2)

    # All commits
    res = await client.get(f"/repos/{repo.id}/commits", cookies=cookies)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2

    # Filter by author alice
    res_filtered = await client.get(f"/repos/{repo.id}/commits?author=alice", cookies=cookies)
    assert res_filtered.status_code == 200
    filtered_items = res_filtered.json()
    assert len(filtered_items) == 1
    assert filtered_items[0]["author_login"] == "alice"


@pytest.mark.asyncio
async def test_list_repo_pulls_and_issues(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
):
    """GET /repos/{id}/pulls and /repos/{id}/issues return items with state filtering."""
    from datetime import UTC, datetime

    from app.models.issue import Issue
    from app.models.pull_request import PullRequest

    user, cookies = create_authenticated_user(fake_db)
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=701,
        full_name="testuser/items-repo",
        status="ready",
    )
    fake_db.add(repo)

    # PRs: 1 open, 1 closed
    pr1 = PullRequest(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=1,
        title="Open PR",
        state="open",
        author_login="charlie",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    pr2 = PullRequest(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=2,
        title="Closed PR",
        state="closed",
        author_login="charlie",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    fake_db.add(pr1)
    fake_db.add(pr2)

    # Issues: 1 open, 1 closed
    issue1 = Issue(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=10,
        title="Open issue",
        state="open",
        labels=[{"name": "bug"}],
        author_login="dave",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    issue2 = Issue(
        id=uuid.uuid4(),
        repo_id=repo.id,
        number=20,
        title="Closed issue",
        state="closed",
        labels=[{"name": "enhancement"}],
        author_login="dave",
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
    )
    fake_db.add(issue1)
    fake_db.add(issue2)

    # PRs: all vs open
    res_all_prs = await client.get(f"/repos/{repo.id}/pulls", cookies=cookies)
    assert res_all_prs.status_code == 200
    assert len(res_all_prs.json()) == 2

    res_open_prs = await client.get(f"/repos/{repo.id}/pulls?state=open", cookies=cookies)
    assert res_open_prs.status_code == 200
    assert len(res_open_prs.json()) == 1
    assert res_open_prs.json()[0]["number"] == 1

    # Issues: all vs closed
    res_all_issues = await client.get(f"/repos/{repo.id}/issues", cookies=cookies)
    assert res_all_issues.status_code == 200
    assert len(res_all_issues.json()) == 2

    res_closed_issues = await client.get(f"/repos/{repo.id}/issues?state=closed", cookies=cookies)
    assert res_closed_issues.status_code == 200
    assert len(res_closed_issues.json()) == 1
    assert res_closed_issues.json()[0]["number"] == 20


@pytest.mark.asyncio
async def test_trigger_repo_indexing_and_status(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    monkeypatch,
):
    """POST /repos/{id}/index triggers indexing job and updates repo status."""
    from unittest.mock import AsyncMock

    user, cookies = create_authenticated_user(fake_db)
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=501,
        full_name="testuser/repo-to-index",
        status="ready",
        index_status="none",
    )
    fake_db.add(repo)

    # 1. Unauthenticated -> 401
    res_unauth = await client.post(f"/repos/{repo.id}/index")
    assert res_unauth.status_code == 401

    # 2. Unknown repo -> 404
    res_404 = await client.post(f"/repos/{uuid.uuid4()}/index", cookies=cookies)
    assert res_404.status_code == 404

    # 3. Successful trigger -> 202
    monkeypatch.setattr("app.api.routes.repos.enqueue_index_job", AsyncMock(return_value="arq-job-123"))

    res_trigger = await client.post(f"/repos/{repo.id}/index", cookies=cookies)
    assert res_trigger.status_code == 202
    data = res_trigger.json()
    assert data["repo_id"] == str(repo.id)
    assert data["status"] == "running"
    assert data["stage"] == "queued"
    assert repo.index_status == "indexing"

    # 4. Already indexing -> 409 Conflict
    res_conflict = await client.post(f"/repos/{repo.id}/index", cookies=cookies)
    assert res_conflict.status_code == 409

    # 5. GET /repos/{id}/index-status -> 200
    res_status = await client.get(f"/repos/{repo.id}/index-status", cookies=cookies)
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["repo_id"] == str(repo.id)
    assert status_data["status"] == "running"


@pytest.mark.asyncio
async def test_search_repo_codebase_validation_and_results(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
    monkeypatch,
):
    """POST /repos/{id}/search validates status and returns search results."""
    from unittest.mock import AsyncMock

    from app.services.search import SearchResultItem

    user, cookies = create_authenticated_user(fake_db)
    repo = Repository(
        id=uuid.uuid4(),
        user_id=user.id,
        github_id=601,
        full_name="testuser/repo-searchable",
        status="ready",
        index_status="none",
    )
    fake_db.add(repo)

    # 1. Repo not indexed -> 409 Conflict
    res_not_ready = await client.post(
        f"/repos/{repo.id}/search",
        json={"query": "test query", "mode": "hybrid"},
        cookies=cookies,
    )
    assert res_not_ready.status_code == 409
    assert "not been indexed yet" in res_not_ready.json()["detail"]

    # 2. Empty query -> 422 Unprocessable Entity
    repo.index_status = "ready"
    res_empty_q = await client.post(
        f"/repos/{repo.id}/search",
        json={"query": "", "mode": "hybrid"},
        cookies=cookies,
    )
    assert res_empty_q.status_code == 422

    # 3. Successful search
    mock_item = SearchResultItem(
        id=uuid.uuid4(),
        path="src/main.py",
        start_line=10,
        end_line=25,
        language="python",
        symbol="main_service",
        kind="function",
        score=0.032,
        snippet="def main_service(): pass",
        permalink="https://github.com/testuser/repo-searchable/blob/main/src/main.py#L10-L25",
    )
    monkeypatch.setattr(
        "app.api.routes.repos.execute_code_search",
        AsyncMock(return_value=[mock_item]),
    )

    res_search = await client.post(
        f"/repos/{repo.id}/search",
        json={"query": "main service", "mode": "hybrid", "limit": 5},
        cookies=cookies,
    )
    assert res_search.status_code == 200
    results = res_search.json()
    assert len(results) == 1
    assert results[0]["path"] == "src/main.py"
    assert results[0]["symbol"] == "main_service"
    assert results[0]["start_line"] == 10
    assert results[0]["end_line"] == 25
    assert results[0]["permalink"] == "https://github.com/testuser/repo-searchable/blob/main/src/main.py#L10-L25"

