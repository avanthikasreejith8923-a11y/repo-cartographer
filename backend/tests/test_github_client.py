"""Unit and integration tests for GitHubClient with respx mocks."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.security import encrypt_token
from app.services.github_client import (
    GitHubAPIError,
    GitHubClient,
    GitHubRateLimitExhaustedError,
    GitHubSecondaryRateLimitError,
)


@pytest.fixture
def encrypted_token() -> str:
    """Fixture returning Fernet-encrypted fake GitHub token."""
    return encrypt_token("ghp_testfaketoken1234567890abcdef")


@pytest.mark.asyncio
async def test_client_decrypts_token_and_sends_headers(encrypted_token: str):
    """Verify GitHubClient decrypts token at request time and sets standard headers."""
    client = GitHubClient(encrypted_token=encrypted_token)
    assert repr(client) == "<GitHubClient authenticated=True>"
    assert "ghp_" not in repr(client)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        route = respx_mock.get(path="/user/repos").respond(
            status_code=200,
            json=[{"id": 1, "name": "repo1"}],
        )

        repos = await client.list_user_repos()
        assert len(repos) == 1
        assert repos[0]["name"] == "repo1"
        assert route.called

        request = route.calls.last.request
        assert request.headers["authorization"] == "Bearer ghp_testfaketoken1234567890abcdef"
        assert request.headers["accept"] == "application/vnd.github+json"
        assert request.headers["x-github-api-version"] == "2022-11-28"


@pytest.mark.asyncio
async def test_client_pagination_follows_link_headers(encrypted_token: str):
    """Verify generic pagination follows RFC 5988 Link headers until no next link."""
    client = GitHubClient(encrypted_token=encrypted_token)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        route = respx_mock.get(path="/repos/octocat/Hello-World/commits")
        route.side_effect = [
            httpx.Response(
                status_code=200,
                json=[{"sha": "c1"}, {"sha": "c2"}],
                headers={
                    "Link": '<https://api.github.com/repos/octocat/Hello-World/commits?page=2>; rel="next"',
                },
            ),
            httpx.Response(
                status_code=200,
                json=[{"sha": "c3"}],
            ),
        ]

        commits = await client.list_commits("octocat", "Hello-World")
        assert len(commits) == 3
        assert [c["sha"] for c in commits] == ["c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_client_pagination_respects_max_items(encrypted_token: str):
    """Verify pagination terminates as soon as max_items is satisfied."""
    client = GitHubClient(encrypted_token=encrypted_token)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World/commits").respond(
            status_code=200,
            json=[{"sha": "c1"}, {"sha": "c2"}, {"sha": "c3"}],
            headers={
                "Link": '<https://api.github.com/repos/octocat/Hello-World/commits?page=2>; rel="next"',
            },
        )

        commits = await client.list_commits("octocat", "Hello-World", max_items=2)
        assert len(commits) == 2
        assert [c["sha"] for c in commits] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_primary_rate_limit_exhausted_raises_error(encrypted_token: str):
    """Verify 403 with 0 remaining rate limit raises GitHubRateLimitExhaustedError."""
    client = GitHubClient(encrypted_token=encrypted_token, max_retries=1)

    reset_epoch = 1770000000
    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World").respond(
            status_code=403,
            json={"message": "API rate limit exceeded for user"},
            headers={
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": str(reset_epoch),
            },
        )

        with pytest.raises(GitHubRateLimitExhaustedError) as exc_info:
            await client.get_repo("octocat", "Hello-World")

        err = exc_info.value
        assert err.reset_timestamp == reset_epoch
        assert err.reset_datetime == datetime.fromtimestamp(reset_epoch, tz=UTC)
        assert client.rate_limit_remaining == 0


@pytest.mark.asyncio
async def test_secondary_rate_limit_retry_after(encrypted_token: str):
    """Verify secondary rate limit (429 / 403) with Retry-After header retries and succeeds."""
    client = GitHubClient(encrypted_token=encrypted_token, max_retries=2, backoff_factor=0.01)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        route = respx_mock.get(path="/repos/octocat/Hello-World/pulls")
        route.side_effect = [
            httpx.Response(
                status_code=429,
                headers={"Retry-After": "0.01"},
                json={"message": "Too Many Requests"},
            ),
            httpx.Response(
                status_code=200,
                json=[{"number": 42, "title": "Add feature"}],
            ),
        ]

        pulls = await client.list_pull_requests("octocat", "Hello-World")
        assert len(pulls) == 1
        assert pulls[0]["number"] == 42
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_server_5xx_exponential_backoff_retry(encrypted_token: str):
    """Verify 5xx server errors trigger exponential backoff retry and eventual recovery."""
    client = GitHubClient(encrypted_token=encrypted_token, max_retries=3, backoff_factor=0.01)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        route = respx_mock.get(path="/repos/octocat/Hello-World/issues")
        route.side_effect = [
            httpx.Response(status_code=502, text="Bad Gateway"),
            httpx.Response(status_code=503, text="Service Unavailable"),
            httpx.Response(
                status_code=200,
                json=[{"number": 1, "title": "Bug report"}],
            ),
        ]

        issues = await client.list_issues("octocat", "Hello-World")
        assert len(issues) == 1
        assert issues[0]["number"] == 1
        assert route.call_count == 3


@pytest.mark.asyncio
async def test_max_retries_exceeded_raises_error(encrypted_token: str):
    """Verify persistent 500 error raises GitHubAPIError after max_retries."""
    client = GitHubClient(encrypted_token=encrypted_token, max_retries=2, backoff_factor=0.01)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World/commits/abc1234").respond(
            status_code=500,
            text="Internal Server Error",
        )

        with pytest.raises(GitHubAPIError) as exc_info:
            await client.get_commit("octocat", "Hello-World", "abc1234")

        assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_secondary_rate_limit_exceeded_raises(encrypted_token: str):
    """Verify continuous secondary rate limit raises GitHubSecondaryRateLimitError."""
    client = GitHubClient(encrypted_token=encrypted_token, max_retries=1, backoff_factor=0.01)

    with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get(path="/repos/octocat/Hello-World/pulls/10").respond(
            status_code=403,
            text="You have triggered an abuse detection mechanism / secondary rate limit.",
            headers={"Retry-After": "0.01"},
        )

        with pytest.raises(GitHubSecondaryRateLimitError):
            await client.get_pull_request("octocat", "Hello-World", 10)
