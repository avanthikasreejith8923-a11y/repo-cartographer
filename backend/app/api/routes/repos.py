"""API routes for repository discovery, import, and management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.schemas.repository import (
    AvailableRepoResponse,
    RepoImportRequest,
    RepoImportResponse,
    RepoResponse,
)
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.queue import enqueue_sync_job

router = APIRouter()


@router.get(
    "/available",
    response_model=list[AvailableRepoResponse],
    summary="List available GitHub repositories for current user",
)
async def list_available_repos(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AvailableRepoResponse]:
    """Fetch user's repositories from GitHub and flag whether each is already imported."""
    client = GitHubClient(encrypted_token=current_user.encrypted_access_token)
    try:
        gh_repos = await client.list_user_repos(per_page=per_page, max_items=page * per_page)
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch repositories from GitHub: {exc}",
        ) from exc

    # Slice for the requested page
    start_idx = (page - 1) * per_page
    paged_repos = gh_repos[start_idx : start_idx + per_page]

    # Query already imported GitHub IDs for this user
    stmt = select(Repository.github_id).where(Repository.user_id == current_user.id)
    result = await db.execute(stmt)
    imported_github_ids = set(result.scalars().all())

    response: list[AvailableRepoResponse] = []
    for repo in paged_repos:
        repo_id = repo.get("id")
        response.append(
            AvailableRepoResponse(
                github_id=repo_id,
                name=repo.get("name", ""),
                full_name=repo.get("full_name", ""),
                description=repo.get("description"),
                is_private=repo.get("private", False),
                html_url=repo.get("html_url"),
                default_branch=repo.get("default_branch", "main"),
                language=repo.get("language"),
                is_imported=repo_id in imported_github_ids,
            )
        )

    return response


@router.post(
    "/import",
    response_model=RepoImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import a GitHub repository and queue async synchronization",
)
async def import_repository(
    payload: RepoImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoImportResponse:
    """Import a GitHub repository by full_name ('owner/repo') and enqueue a sync job."""
    owner, repo_name = payload.full_name.split("/", 1)
    client = GitHubClient(encrypted_token=current_user.encrypted_access_token)

    try:
        repo_data = await client.get_repo(owner=owner, repo=repo_name)
    except GitHubAPIError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{payload.full_name}' was not found on GitHub or you lack access.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch repository from GitHub: {exc}",
        ) from exc

    github_id = repo_data["id"]

    # Check if already imported by this user
    existing_stmt = select(Repository).where(
        Repository.user_id == current_user.id,
        Repository.github_id == github_id,
    )
    existing_res = await db.execute(existing_stmt)
    existing_repo = existing_res.scalar_one_or_none()
    if existing_repo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository '{payload.full_name}' is already imported.",
        )

    # Create new Repository record
    repo = Repository(
        user_id=current_user.id,
        github_id=github_id,
        full_name=repo_data.get("full_name", payload.full_name),
        description=repo_data.get("description"),
        default_branch=repo_data.get("default_branch", "main"),
        language=repo_data.get("language"),
        is_private=repo_data.get("private", False),
        status="pending",
    )
    db.add(repo)
    await db.flush()

    # Create initial SyncJob
    sync_job = SyncJob(
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
    )
    db.add(sync_job)
    await db.commit()

    # Enqueue background sync job
    await enqueue_sync_job(repo.id)

    return RepoImportResponse(
        repository=repo,  # type: ignore[arg-type]
        sync_job=sync_job,  # type: ignore[arg-type]
    )


@router.get(
    "",
    response_model=list[RepoResponse],
    summary="List all repositories imported by the current user",
)
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoResponse]:
    """Retrieve all repositories belonging to the authenticated user."""
    stmt = (
        select(Repository)
        .where(Repository.user_id == current_user.id)
        .order_by(Repository.created_at.desc())
    )
    result = await db.execute(stmt)
    repos = result.scalars().all()
    return [RepoResponse.model_validate(r) for r in repos]


@router.get(
    "/{repo_id}",
    response_model=RepoResponse,
    summary="Get repository details with ownership enforcement",
)
async def get_repository(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoResponse:
    """Retrieve a single repository. Enforces user ownership; returns 404 if not found or unauthorized."""
    stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    return RepoResponse.model_validate(repo)


@router.delete(
    "/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an imported repository",
)
async def delete_repository(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a repository and its cascading records. Returns 404 if not found or not owned."""
    stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    await db.delete(repo)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
