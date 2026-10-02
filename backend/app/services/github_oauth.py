"""GitHub OAuth service handling authentication URL construction, code exchange, profile retrieval, and user upsert."""

import urllib.parse
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.security import encrypt_token
from app.models.user import User

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
GITHUB_SCOPES = "read:user user:email repo"


class GitHubOAuthError(Exception):
    """Exception raised during GitHub OAuth interaction failures."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class GitHubOAuthService:
    """Service wrapping GitHub OAuth web application flow and profile fetching."""

    def __init__(self) -> None:
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
        self.redirect_uri = settings.GITHUB_REDIRECT_URI

    def build_authorization_url(self, state: str) -> str:
        """Construct the GitHub authorization URL including client ID, redirect URI, scope, and state."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": GITHUB_SCOPES,
            "state": state,
        }
        return f"{GITHUB_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        """Exchange temporary OAuth code for a GitHub access token."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "repo-cartographer",
        }
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(GITHUB_TOKEN_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error(f"Failed to exchange OAuth code with GitHub: {exc}")
                raise GitHubOAuthError("GitHub token exchange network failure", status_code=502) from exc

        if "error" in data:
            error_desc = data.get("error_description", data["error"])
            logger.error(f"GitHub OAuth token exchange error: {error_desc}")
            raise GitHubOAuthError(f"OAuth exchange failed: {error_desc}", status_code=400)

        access_token = data.get("access_token")
        if not access_token:
            raise GitHubOAuthError("No access token returned from GitHub", status_code=502)

        return str(access_token)

    async def fetch_github_user_profile(self, access_token: str) -> dict[str, Any]:
        """Fetch user profile and primary verified email from GitHub API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "repo-cartographer",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                user_res = await client.get(GITHUB_USER_URL, headers=headers)
                user_res.raise_for_status()
                profile_data = user_res.json()
            except httpx.HTTPError as exc:
                logger.error(f"Failed to fetch user profile from GitHub API: {exc}")
                raise GitHubOAuthError("Failed to fetch user profile from GitHub", status_code=502) from exc

            email = profile_data.get("email")

            # If email is private/null in profile, query /user/emails endpoint
            if not email:
                try:
                    email_res = await client.get(GITHUB_EMAILS_URL, headers=headers)
                    if email_res.status_code == 200:
                        emails: list[dict[str, Any]] = email_res.json()
                        # Prefer primary + verified email
                        for entry in emails:
                            if entry.get("primary") and entry.get("verified"):
                                email = entry.get("email")
                                break
                        # Fallback to any verified email
                        if not email:
                            for entry in emails:
                                if entry.get("verified"):
                                    email = entry.get("email")
                                    break
                except httpx.HTTPError as exc:
                    logger.warning(f"Could not retrieve secondary emails from GitHub: {exc}")

        return {
            "github_id": profile_data["id"],
            "login": profile_data["login"],
            "name": profile_data.get("name"),
            "avatar_url": profile_data.get("avatar_url"),
            "email": email,
        }

    async def upsert_user(
        self,
        session: AsyncSession,
        profile: dict[str, Any],
        access_token: str,
    ) -> User:
        """Upsert user profile in database and store Fernet-encrypted GitHub access token."""
        encrypted_token = encrypt_token(access_token)
        github_id = profile["github_id"]

        stmt = select(User).where(User.github_id == github_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Update existing user
            user.login = profile["login"]
            user.name = profile.get("name")
            user.avatar_url = profile.get("avatar_url")
            user.email = profile.get("email")
            user.encrypted_access_token = encrypted_token
        else:
            # Create new user
            user = User(
                github_id=github_id,
                login=profile["login"],
                name=profile.get("name"),
                avatar_url=profile.get("avatar_url"),
                email=profile.get("email"),
                encrypted_access_token=encrypted_token,
            )
            session.add(user)

        await session.flush()
        return user


github_oauth_service = GitHubOAuthService()
