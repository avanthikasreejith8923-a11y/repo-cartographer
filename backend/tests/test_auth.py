"""Tests for GitHub OAuth initiation, callback, session verification, and logout."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.security import create_session_token, encrypt_token, sign_oauth_state
from app.models.user import User
from app.services.github_oauth import GITHUB_TOKEN_URL, GITHUB_USER_URL
from tests.conftest import InMemoryAsyncSession


@pytest.mark.asyncio
async def test_github_login_redirect_and_state_cookie(client: httpx.AsyncClient) -> None:
    """Verify /auth/github/login sets a signed state cookie and redirects to GitHub with proper scopes."""
    response = await client.get("/auth/github/login", follow_redirects=False)
    assert response.status_code == 302

    redirect_url = response.headers.get("location", "")
    assert "https://github.com/login/oauth/authorize" in redirect_url
    assert f"client_id={settings.GITHUB_CLIENT_ID}" in redirect_url
    assert "scope=read%3Auser+user%3Aemail+repo" in redirect_url or "scope=read:user+user:email+repo" in redirect_url
    assert "state=" in redirect_url

    # Check OAuth state cookie
    assert settings.OAUTH_STATE_COOKIE_NAME in response.cookies
    state_cookie = response.cookies[settings.OAUTH_STATE_COOKIE_NAME]
    assert "." in state_cookie  # Signed value format state.signature


@pytest.mark.asyncio
async def test_github_callback_state_mismatch_rejected(client: httpx.AsyncClient) -> None:
    """Verify callback rejects requests with state mismatch or missing state cookie."""
    # 1. Missing cookie
    res_no_cookie = await client.get("/auth/github/callback?code=mock_code&state=fake_state")
    assert res_no_cookie.status_code == 400
    assert "state" in res_no_cookie.json()["detail"].lower()

    # 2. Tampered / mismatched cookie
    client.cookies.set(settings.OAUTH_STATE_COOKIE_NAME, "tampered_state.bad_signature")
    res_tampered = await client.get("/auth/github/callback?code=mock_code&state=real_state")
    assert res_tampered.status_code == 400


@pytest.mark.asyncio
@respx.mock
async def test_github_callback_success_flow(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
) -> None:
    """Verify full OAuth callback flow: exchange code, fetch profile, upsert user, issue session cookie."""
    raw_state = "valid_secure_random_state_string"
    signed_state = sign_oauth_state(raw_state)
    client.cookies.set(settings.OAUTH_STATE_COOKIE_NAME, signed_state)

    # Mock GitHub OAuth Token Exchange
    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "gho_sample_access_token_12345", "token_type": "bearer", "scope": "repo,read:user"},
        )
    )

    # Mock GitHub User Profile API
    respx.get(GITHUB_USER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 98765432,
                "login": "octo-engineer",
                "name": "Octo Engineer",
                "avatar_url": "https://avatars.githubusercontent.com/u/98765432",
                "email": "engineer@octo.org",
            },
        )
    )

    response = await client.get(
        f"/auth/github/callback?code=valid_github_code&state={raw_state}",
        follow_redirects=False,
    )

    # Should redirect to frontend dashboard
    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.FRONTEND_URL}/dashboard"

    # Verify session cookie was set
    assert settings.SESSION_COOKIE_NAME in response.cookies
    session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert len(session_cookie) > 20

    # Verify state cookie was cleared
    # In httpx, cleared cookies typically have empty value or max-age=0
    deleted_state_cookie = response.cookies.get(settings.OAUTH_STATE_COOKIE_NAME)
    assert deleted_state_cookie is None or deleted_state_cookie == '""'

    # Verify user was saved in database
    assert 98765432 in fake_db.users_by_github_id
    saved_user = fake_db.users_by_github_id[98765432]
    assert saved_user.login == "octo-engineer"
    assert saved_user.email == "engineer@octo.org"
    assert saved_user.encrypted_access_token != "gho_sample_access_token_12345"


@pytest.mark.asyncio
async def test_auth_me_unauthenticated_returns_401(client: httpx.AsyncClient) -> None:
    """Verify /auth/me returns 401 Unauthorized without session cookie."""
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_auth_me_authenticated_returns_user_data(
    client: httpx.AsyncClient,
    fake_db: InMemoryAsyncSession,
) -> None:
    """Verify /auth/me returns current user information with a valid session cookie."""
    user_id = uuid.uuid4()
    test_user = User(
        id=user_id,
        github_id=45678,
        login="testpilot",
        name="Test Pilot",
        avatar_url="https://github.com/testpilot.png",
        email="pilot@test.com",
        encrypted_access_token=encrypt_token("gho_secret_token"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    fake_db.add(test_user)

    # Create session JWT
    token = create_session_token({"sub": str(user_id), "github_id": 45678, "login": "testpilot"})
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)

    response = await client.get("/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(user_id)
    assert data["login"] == "testpilot"
    assert data["name"] == "Test Pilot"
    assert data["email"] == "pilot@test.com"
    # Ensure encrypted token is NOT leaked in UserRead schema
    assert "encrypted_access_token" not in data


@pytest.mark.asyncio
async def test_auth_logout(client: httpx.AsyncClient) -> None:
    """Verify POST /auth/logout clears session cookie and returns success response."""
    client.cookies.set(settings.SESSION_COOKIE_NAME, "mock_jwt_session_token")
    response = await client.post("/auth/logout")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False
    assert "terminated" in data["message"]


@pytest.mark.asyncio
async def test_auth_demo_login(client: httpx.AsyncClient) -> None:
    """Verify POST /auth/demo-login sets session cookie and returns demo user."""
    response = await client.post("/auth/demo-login")
    assert response.status_code == 200
    data = response.json()
    assert data["login"] == "avanthikasreejith8923-a11y"
    assert "rc_session" in response.cookies or settings.SESSION_COOKIE_NAME in response.cookies
