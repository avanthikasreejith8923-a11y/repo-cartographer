"""Async GitHub API Client with generic RFC 5988 pagination and token decryption."""

import re
from typing import Any

import httpx

from app.core.logging import logger
from app.core.security import decrypt_token


class GitHubAPIError(Exception):
    """Exception raised when a GitHub API request fails."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GitHubClient:
    """Asynchronous client for interacting with the GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(self, encrypted_token: str):
        """Initialize client with Fernet-encrypted GitHub personal access token."""
        self._encrypted_token = encrypted_token

    def _get_auth_headers(self) -> dict[str, str]:
        """Decrypt token at call-time and return authorization headers.

        The plaintext token is never persisted on self or logged.
        """
        token = decrypt_token(self._encrypted_token)
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-cartographer",
        }

    def _parse_next_link(self, link_header: str | None) -> str | None:
        """Parse RFC 5988 Link header for rel='next' URL."""
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        if match:
            return match.group(1)
        return None

    async def _request(
        self,
        method: str,
        url_or_path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute HTTP request against GitHub API with authorization headers."""
        url = url_or_path if url_or_path.startswith("http") else f"{self.BASE_URL}{url_or_path}"
        headers = self._get_auth_headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
            )

        if response.status_code >= 400:
            logger.warning(
                f"GitHub API error {response.status_code} on {method} {url}"
            )
            raise GitHubAPIError(
                f"GitHub API request failed with status {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )

        return response

    async def paginate(
        self,
        url_or_path: str,
        params: dict[str, Any] | None = None,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch items across multiple pages following RFC 5988 Link header until max_items reached."""
        results: list[dict[str, Any]] = []
        next_url: str | None = url_or_path
        current_params = params.copy() if params else {}

        while next_url:
            response = await self._request("GET", next_url, params=current_params)
            data = response.json()
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict) and "items" in data:
                results.extend(data["items"])
            else:
                break

            if max_items is not None and len(results) >= max_items:
                results = results[:max_items]
                break

            next_url = self._parse_next_link(response.headers.get("Link"))
            current_params = None  # URL in Link header already encodes pagination query params

        return results

    async def list_user_repos(
        self,
        affiliation: str = "owner,collaborator,organization_member",
        per_page: int = 100,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """List repositories accessible to the authenticated user."""
        return await self.paginate(
            "/user/repos",
            params={
                "affiliation": affiliation,
                "per_page": min(per_page, 100),
                "sort": "updated",
            },
            max_items=max_items,
        )

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch detailed metadata for a single repository."""
        response = await self._request("GET", f"/repos/{owner}/{repo}")
        return response.json()

    async def list_commits(
        self,
        owner: str,
        repo: str,
        since: str | None = None,
        until: str | None = None,
        author: str | None = None,
        max_items: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch commit history for a repository."""
        params: dict[str, Any] = {"per_page": 100}
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if author:
            params["author"] = author

        return await self.paginate(
            f"/repos/{owner}/{repo}/commits",
            params=params,
            max_items=max_items,
        )

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        """Fetch single commit details including statistics (additions, deletions)."""
        response = await self._request("GET", f"/repos/{owner}/{repo}/commits/{sha}")
        return response.json()

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        max_items: int = 200,
    ) -> list[dict[str, Any]]:
        """Fetch pull requests for a repository."""
        params = {
            "state": state,
            "per_page": 100,
            "sort": "created",
            "direction": "desc",
        }
        return await self.paginate(
            f"/repos/{owner}/{repo}/pulls",
            params=params,
            max_items=max_items,
        )

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """Fetch single pull request details including additions, deletions, and changed_files."""
        response = await self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return response.json()

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        since: str | None = None,
        max_items: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch issues for a repository (note: caller or consumer filters out PRs)."""
        params: dict[str, Any] = {
            "state": state,
            "per_page": 100,
            "sort": "created",
            "direction": "desc",
        }
        if since:
            params["since"] = since

        return await self.paginate(
            f"/repos/{owner}/{repo}/issues",
            params=params,
            max_items=max_items,
        )

    def __repr__(self) -> str:
        return "<GitHubClient authenticated=True>"
