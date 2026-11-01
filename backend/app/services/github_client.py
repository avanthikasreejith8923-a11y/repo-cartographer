"""Async GitHub API Client with rate limit tracking, exponential backoff, and pagination."""

import asyncio
import re
from datetime import UTC, datetime
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


class GitHubRateLimitExhaustedError(GitHubAPIError):
    """Exception raised when primary GitHub API rate limit is fully exhausted."""

    def __init__(self, message: str, reset_timestamp: int | None = None, status_code: int = 403):
        super().__init__(message, status_code=status_code)
        self.reset_timestamp = reset_timestamp

    @property
    def reset_datetime(self) -> datetime | None:
        """UTC datetime when the primary rate limit resets."""
        if self.reset_timestamp:
            return datetime.fromtimestamp(self.reset_timestamp, tz=UTC)
        return None


class GitHubSecondaryRateLimitError(GitHubAPIError):
    """Exception raised when hitting secondary rate limits or abuse detection."""

    def __init__(self, message: str, retry_after: float | None = None, status_code: int = 403):
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


class GitHubClient:
    """Asynchronous client for interacting with the GitHub REST API."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        encrypted_token: str,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        timeout: float = 30.0,
    ):
        """Initialize client with Fernet-encrypted GitHub personal access token."""
        self._encrypted_token = encrypted_token
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: int | None = None
        self.rate_limit_limit: int | None = None
        self._unauthenticated_fallback: bool = False

    def _get_auth_headers(self) -> dict[str, str]:
        """Decrypt token at call-time and return authorization headers.

        The plaintext token is never persisted on self or logged.
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-cartographer",
        }
        if not getattr(self, "_unauthenticated_fallback", False):
            try:
                token = decrypt_token(self._encrypted_token)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except Exception:
                pass
        return headers

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """Update tracked rate limit attributes from response headers."""
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        limit = response.headers.get("x-ratelimit-limit")

        if remaining is not None:
            try:
                self.rate_limit_remaining = int(remaining)
            except ValueError:
                pass
        if reset is not None:
            try:
                self.rate_limit_reset = int(reset)
            except ValueError:
                pass
        if limit is not None:
            try:
                self.rate_limit_limit = int(limit)
            except ValueError:
                pass

    def _parse_next_link(self, link_header: str | None) -> str | None:
        """Parse RFC 5988 Link header for rel='next' URL."""
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        if match:
            return match.group(1)
        return None

    def _get_retry_after(self, response: httpx.Response) -> float | None:
        """Extract Retry-After duration in seconds from response headers if present."""
        retry_header = response.headers.get("Retry-After")
        if retry_header:
            try:
                return float(retry_header)
            except ValueError:
                pass
        return None

    def _is_secondary_rate_limit(self, response: httpx.Response) -> bool:
        """Detect whether a response indicates GitHub secondary rate limit."""
        if response.status_code == 429:
            return True
        if response.status_code == 403:
            body = response.text.lower()
            return "secondary rate limit" in body or "please wait a few minutes" in body
        return False

    async def _request(
        self,
        method: str,
        url_or_path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with exponential backoff and rate limit tracking."""
        url = url_or_path if url_or_path.startswith("http") else f"{self.BASE_URL}{url_or_path}"
        headers = self._get_auth_headers()

        attempt = 0
        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                    )

                self._update_rate_limits(response)

                # Fallback to unauthenticated request on 401 (e.g. invalid/expired token for public repos)
                if response.status_code == 401 and "Authorization" in headers:
                    logger.warning(
                        "GitHub token rejected, using unauthenticated access (public repos only, 60 requests/hour)"
                    )
                    self._unauthenticated_fallback = True
                    headers.pop("Authorization", None)
                    continue

                # Check primary rate limit exhaustion
                if response.status_code == 403 and self.rate_limit_remaining == 0:
                    reset_str = (
                        datetime.fromtimestamp(self.rate_limit_reset, tz=UTC).isoformat()
                        if self.rate_limit_reset
                        else "unknown"
                    )
                    raise GitHubRateLimitExhaustedError(
                        f"GitHub API primary rate limit exhausted. Resets at {reset_str}.",
                        reset_timestamp=self.rate_limit_reset,
                    )

                # Check secondary rate limit (429 or 403 secondary)
                if self._is_secondary_rate_limit(response):
                    retry_after = self._get_retry_after(response) or (self.backoff_factor * (2 ** (attempt - 1)))
                    if attempt <= self.max_retries:
                        logger.warning(
                            f"GitHub secondary rate limit encountered on {method} {url}. "
                            f"Retrying in {retry_after:.1f}s (attempt {attempt}/{self.max_retries})."
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise GitHubSecondaryRateLimitError(
                        f"GitHub API secondary rate limit exceeded after {attempt} attempts.",
                        retry_after=retry_after,
                        status_code=response.status_code,
                    )

                # Check 5xx server errors
                if 500 <= response.status_code < 600:
                    if attempt <= self.max_retries:
                        delay = self.backoff_factor * (2 ** (attempt - 1))
                        logger.warning(
                            f"GitHub API returned {response.status_code} on {method} {url}. "
                            f"Retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})."
                        )
                        await asyncio.sleep(delay)
                        continue

                # Raise for any remaining 4xx/5xx errors
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

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt <= self.max_retries:
                    delay = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        f"Network exception ({type(exc).__name__}) contacting GitHub on {method} {url}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt}/{self.max_retries})."
                    )
                    await asyncio.sleep(delay)
                    continue
                raise GitHubAPIError(f"GitHub network communication failure: {exc}") from exc

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

    async def list_pull_request_files(
        self,
        owner: str,
        repo: str,
        number: int,
        max_items: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch files changed in a pull request.

        Items contain filename, status, additions, deletions, and patch (if available).
        """
        params = {"per_page": 100}
        return await self.paginate(
            f"/repos/{owner}/{repo}/pulls/{number}/files",
            params=params,
            max_items=max_items,
        )

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
