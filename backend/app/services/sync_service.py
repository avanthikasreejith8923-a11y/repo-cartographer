"""Repository synchronization pipeline handling background ingestion and stage progress."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.services.github_client import GitHubAPIError, GitHubClient


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

        # Placeholders for stages 2, 3, 4 (implemented in subsequent commits)
        # Marking ready after metadata stage for Commit 9
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
