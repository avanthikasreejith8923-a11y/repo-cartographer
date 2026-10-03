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
