"""Repository synchronization pipeline handling background ingestion and stage progress."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.commit import Commit
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.services.github_client import GitHubAPIError, GitHubClient


def parse_github_datetime(date_str: str | None) -> datetime:
    """Parse ISO 8601 GitHub datetime string to timezone-aware UTC datetime."""
    if not date_str:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(UTC)


async def sync_metadata_stage(
    repo: Repository,
    client: GitHubClient,
    db: AsyncSession,
) -> dict[str, Any]:
    """Stage 1: Fetch and update latest repository metadata from GitHub."""
    owner, repo_name = repo.full_name.split("/", 1)
    logger.info(f"Sync stage [metadata]: Fetching {owner}/{repo_name}")
    repo_data = await client.get_repo(owner=owner, repo=repo_name)

    repo.description = repo_data.get("description")
    repo.default_branch = repo_data.get("default_branch", repo.default_branch or "main")
    repo.language = repo_data.get("language")
    repo.is_private = repo_data.get("private", False)
    repo.full_name = repo_data.get("full_name", repo.full_name)
    await db.flush()
    return repo_data


async def sync_commits_stage(
    repo: Repository,
    client: GitHubClient,
    db: AsyncSession,
) -> int:
    """Stage 2: Fetch and idempotently upsert commits with additions/deletions stats."""
    owner, repo_name = repo.full_name.split("/", 1)
    logger.info(f"Sync stage [commits]: Fetching commits for {owner}/{repo_name}")
    raw_commits = await client.list_commits(
        owner=owner,
        repo=repo_name,
        max_items=settings.SYNC_MAX_COMMITS,
    )

    upserted_count = 0
    for idx, c in enumerate(raw_commits):
        sha = c["sha"]
        commit_meta = c.get("commit", {})
        author_meta = c.get("author") or {}
        committer_meta = commit_meta.get("committer") or {}
        commit_author = commit_meta.get("author") or {}

        date_str = committer_meta.get("date") or commit_author.get("date")
        committed_at = parse_github_datetime(date_str)

        additions: int | None = None
        deletions: int | None = None
        files_changed: int | None = None

        # Fetch per-item stats only for the most recent N commits to protect rate limits
        if idx < settings.SYNC_STATS_COMMITS_LIMIT:
            try:
                detail = await client.get_commit(owner=owner, repo=repo_name, sha=sha)
                stats = detail.get("stats", {})
                additions = stats.get("additions")
                deletions = stats.get("deletions")
                files_changed = len(detail.get("files", [])) or stats.get("total")
            except Exception as e:
                logger.debug(f"Could not fetch stats for commit {sha[:7]}: {e}")

        insert_stmt = insert(Commit).values(
            repo_id=repo.id,
            sha=sha,
            author_login=author_meta.get("login"),
            author_name=commit_author.get("name"),
            message=commit_meta.get("message", ""),
            committed_at=committed_at,
            additions=additions,
            deletions=deletions,
            files_changed=files_changed,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["repo_id", "sha"],
            set_={
                "author_login": insert_stmt.excluded.author_login,
                "author_name": insert_stmt.excluded.author_name,
                "message": insert_stmt.excluded.message,
                "committed_at": insert_stmt.excluded.committed_at,
                "additions": insert_stmt.excluded.additions,
                "deletions": insert_stmt.excluded.deletions,
                "files_changed": insert_stmt.excluded.files_changed,
                "updated_at": func.now(),
            },
        )
        await db.execute(upsert_stmt)
        upserted_count += 1

    await db.flush()
    return upserted_count


async def sync_pull_requests_stage(
    repo: Repository,
    client: GitHubClient,
    db: AsyncSession,
) -> int:
    """Stage 3: Fetch and idempotently upsert pull requests with additions/deletions stats."""
    owner, repo_name = repo.full_name.split("/", 1)
    logger.info(f"Sync stage [pull_requests]: Fetching PRs for {owner}/{repo_name}")
    raw_prs = await client.list_pull_requests(
        owner=owner,
        repo=repo_name,
        state="all",
        max_items=settings.SYNC_MAX_PRS,
    )

    upserted_count = 0
    for idx, pr in enumerate(raw_prs):
        number = pr["number"]
        author_meta = pr.get("user") or {}
        created_at = parse_github_datetime(pr.get("created_at"))
        merged_at = parse_github_datetime(pr.get("merged_at")) if pr.get("merged_at") else None
        closed_at = parse_github_datetime(pr.get("closed_at")) if pr.get("closed_at") else None

        additions: int | None = None
        deletions: int | None = None
        changed_files: int | None = None

        # Fetch per-item stats only for the most recent N PRs to protect rate limits
        if idx < settings.SYNC_STATS_PRS_LIMIT:
            try:
                detail = await client.get_pull_request(owner=owner, repo=repo_name, number=number)
                additions = detail.get("additions")
                deletions = detail.get("deletions")
                changed_files = detail.get("changed_files")
            except Exception as e:
                logger.debug(f"Could not fetch stats for PR #{number}: {e}")

        insert_stmt = insert(PullRequest).values(
            repo_id=repo.id,
            number=number,
            title=pr.get("title", ""),
            body=pr.get("body"),
            state=pr.get("state", "open"),
            author_login=author_meta.get("login"),
            created_at=created_at,
            merged_at=merged_at,
            closed_at=closed_at,
            additions=additions,
            deletions=deletions,
            changed_files=changed_files,
            base_ref=pr.get("base", {}).get("ref"),
            head_ref=pr.get("head", {}).get("ref"),
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["repo_id", "number"],
            set_={
                "title": insert_stmt.excluded.title,
                "body": insert_stmt.excluded.body,
                "state": insert_stmt.excluded.state,
                "author_login": insert_stmt.excluded.author_login,
                "merged_at": insert_stmt.excluded.merged_at,
                "closed_at": insert_stmt.excluded.closed_at,
                "additions": insert_stmt.excluded.additions,
                "deletions": insert_stmt.excluded.deletions,
                "changed_files": insert_stmt.excluded.changed_files,
                "base_ref": insert_stmt.excluded.base_ref,
                "head_ref": insert_stmt.excluded.head_ref,
                "updated_at": func.now(),
            },
        )
        await db.execute(upsert_stmt)
        upserted_count += 1

    await db.flush()
    return upserted_count


async def execute_repo_sync(repo_id: str | uuid.UUID, db: AsyncSession) -> None:
    """Execute background ingestion pipeline across stages: metadata -> commits -> PRs -> issues."""
    if isinstance(repo_id, str):
        repo_id = uuid.UUID(repo_id)

    # 1. Fetch repository and user
    stmt = select(Repository).where(Repository.id == repo_id)
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()
    if not repo:
        logger.error(f"Sync failed: Repository {repo_id} not found in database.")
        return

    user_stmt = select(User).where(User.id == repo.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if not user:
        logger.error(f"Sync failed: User {repo.user_id} for repo {repo_id} not found.")
        return

    # 2. Get or create active SyncJob
    job_stmt = (
        select(SyncJob)
        .where(SyncJob.repo_id == repo.id)
        .order_by(SyncJob.created_at.desc())
    )
    job_res = await db.execute(job_stmt)
    sync_job = job_res.scalars().first()

    now = datetime.now(UTC)
    if not sync_job or sync_job.status in ("completed", "failed"):
        sync_job = SyncJob(
            repo_id=repo.id,
            status="running",
            stage="queued",
            progress=0,
            started_at=now,
        )
        db.add(sync_job)
    else:
        sync_job.status = "running"
        sync_job.started_at = sync_job.started_at or now

    repo.status = "syncing"
    repo.sync_error = None
    sync_job.error = None
    await db.commit()

    client = GitHubClient(encrypted_token=user.encrypted_access_token)

    try:
        # Stage 1: Metadata
        sync_job.stage = "metadata"
        sync_job.progress = 10
        await db.commit()

        await sync_metadata_stage(repo=repo, client=client, db=db)
        sync_job.progress = 25
        await db.commit()

        # Stage 2: Commits
        sync_job.stage = "commits"
        sync_job.progress = 30
        await db.commit()

        await sync_commits_stage(repo=repo, client=client, db=db)
        sync_job.progress = 50
        await db.commit()

        # Stage 3: Pull Requests
        sync_job.stage = "pull_requests"
        sync_job.progress = 55
        await db.commit()

        await sync_pull_requests_stage(repo=repo, client=client, db=db)
        sync_job.progress = 75
        await db.commit()

        # Placeholders for stage 4 (issues - implemented in commit 12)
        repo.status = "ready"
        repo.last_synced_at = datetime.now(UTC)
        repo.sync_error = None

        sync_job.status = "completed"
        sync_job.stage = "completed"
        sync_job.progress = 100
        sync_job.finished_at = datetime.now(UTC)
        await db.commit()

        logger.info(f"Sync completed successfully for repo {repo.full_name}")

    except Exception as exc:
        err_msg = str(exc)
        if isinstance(exc, GitHubAPIError) and exc.response_body:
            err_msg = f"{exc}: {exc.response_body}"
        logger.exception(f"Sync error on repo {repo.full_name}: {err_msg}")

        repo.status = "failed"
        repo.sync_error = err_msg

        sync_job.status = "failed"
        sync_job.stage = "failed"
        sync_job.error = err_msg
        sync_job.finished_at = datetime.now(UTC)
        await db.commit()
