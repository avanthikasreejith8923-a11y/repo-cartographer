"""API routes for repository discovery, import, and management."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.commit import Commit
from app.models.issue import Issue
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.schemas.repository import (
    AvailableRepoResponse,
    CommitResponse,
    IssueResponse,
    PullRequestResponse,
    RepoImportRequest,
    RepoImportResponse,
    RepoResponse,
    SyncJobResponse,
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
    from app.core.config import settings
    from app.core.security import decrypt_token

    is_demo_user = False
    try:
        raw_token = decrypt_token(current_user.encrypted_access_token)
        is_demo_user = raw_token.startswith("ghp_demo_")
    except Exception:
        pass

    if settings.DEMO_MODE and is_demo_user:
        stmt = select(Repository.github_id).where(Repository.user_id == current_user.id)
        result = await db.execute(stmt)
        imported_github_ids = set(result.scalars().all())

        demo_available = [
            {
                "id": 89230101,
                "name": "repo-cartographer",
                "full_name": "avanthikasreejith8923-a11y/repo-cartographer",
                "description": "AI Developer Productivity Platform: Codebase Graphing, Ingestion, and RAG with Citations",
                "private": False,
                "html_url": "https://github.com/avanthikasreejith8923-a11y/repo-cartographer",
                "default_branch": "main",
                "language": "TypeScript",
            },
            {
                "id": 89230102,
                "name": "fastapi",
                "full_name": "fastapi/fastapi",
                "description": "FastAPI framework, high performance, easy to learn, fast to code, ready for production",
                "private": False,
                "html_url": "https://github.com/fastapi/fastapi",
                "default_branch": "master",
                "language": "Python",
            },
            {
                "id": 89230103,
                "name": "react",
                "full_name": "facebook/react",
                "description": "The library for web and native user interfaces.",
                "private": False,
                "html_url": "https://github.com/facebook/react",
                "default_branch": "main",
                "language": "JavaScript",
            },
            {
                "id": 89230104,
                "name": "flask",
                "full_name": "pallets/flask",
                "description": "The Python micro framework for building web applications.",
                "private": False,
                "html_url": "https://github.com/pallets/flask",
                "default_branch": "main",
                "language": "Python",
            },
            {
                "id": 89230105,
                "name": "transformers",
                "full_name": "huggingface/transformers",
                "description": "State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.",
                "private": False,
                "html_url": "https://github.com/huggingface/transformers",
                "default_branch": "main",
                "language": "Python",
            },
        ]
        return [
            AvailableRepoResponse(
                github_id=r["id"],
                name=r["name"],
                full_name=r["full_name"],
                description=r["description"],
                is_private=r["private"],
                html_url=r["html_url"],
                default_branch=r["default_branch"],
                language=r["language"],
                is_imported=r["id"] in imported_github_ids,
            )
            for r in demo_available
        ]

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
    from app.core.config import settings
    from app.core.security import decrypt_token

    is_demo_user = False
    try:
        raw_token = decrypt_token(current_user.encrypted_access_token)
        is_demo_user = raw_token.startswith("ghp_demo_")
    except Exception:
        pass

    if settings.DEMO_MODE and is_demo_user:
        descriptions = {
            "facebook/react": "The library for web and native user interfaces.",
            "pallets/flask": "The Python micro framework for building web applications.",
            "huggingface/transformers": "State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.",
        }
        repo_data = {
            "id": abs(hash(payload.full_name)) % 100000000 + 1000,
            "full_name": payload.full_name,
            "description": descriptions.get(payload.full_name, f"Imported demo repository: {payload.full_name}"),
            "default_branch": "main",
            "language": "JavaScript" if "react" in payload.full_name else "Python",
            "private": False,
        }
    else:
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


@router.post(
    "/{repo_id}/sync",
    response_model=SyncJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous re-synchronization of a repository",
)
async def trigger_sync(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncJobResponse:
    """Trigger background re-sync for a repository owned by the authenticated user."""
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

    repo.status = "pending"
    repo.sync_error = None

    sync_job = SyncJob(
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
    )
    db.add(sync_job)
    await db.commit()

    await enqueue_sync_job(repo.id)
    return SyncJobResponse.model_validate(sync_job)


@router.get(
    "/{repo_id}/sync-status",
    response_model=SyncJobResponse,
    summary="Get current or latest sync job status and progress for a repository",
)
async def get_sync_status(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncJobResponse:
    """Retrieve the latest sync job status. Returns 404 if repository or sync job is not found."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    job_stmt = (
        select(SyncJob)
        .where(SyncJob.repo_id == repo.id)
        .order_by(SyncJob.created_at.desc())
    )
    job_res = await db.execute(job_stmt)
    sync_job = job_res.scalars().first()
    if not sync_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sync job found for repository",
        )

    return SyncJobResponse.model_validate(sync_job)


@router.get(
    "/{repo_id}/commits",
    response_model=list[CommitResponse],
    summary="List ingested commits for a repository with optional filtering",
)
async def list_repo_commits(
    repo_id: uuid.UUID,
    author: str | None = Query(None, description="Filter by author login or name"),
    since: datetime | None = Query(None, description="Only commits after this timestamp"),
    until: datetime | None = Query(None, description="Only commits before this timestamp"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommitResponse]:
    """Retrieve commits for a repository owned by current user."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    query = select(Commit).where(Commit.repo_id == repo.id)
    if author:
        author_filter = f"%{author}%"
        query = query.where(
            (Commit.author_login.ilike(author_filter)) | (Commit.author_name.ilike(author_filter))
        )
    if since:
        query = query.where(Commit.committed_at >= since)
    if until:
        query = query.where(Commit.committed_at <= until)

    query = query.order_by(Commit.committed_at.desc()).offset(offset).limit(limit)
    res = await db.execute(query)
    commits = res.scalars().all()
    return [CommitResponse.model_validate(c) for c in commits]


@router.get(
    "/{repo_id}/pulls",
    response_model=list[PullRequestResponse],
    summary="List ingested pull requests for a repository with optional filtering",
)
async def list_repo_pull_requests(
    repo_id: uuid.UUID,
    state: str = Query("all", pattern="^(open|closed|all)$", description="Filter by state (open, closed, all)"),
    author: str | None = Query(None, description="Filter by author login"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PullRequestResponse]:
    """Retrieve pull requests for a repository owned by current user."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    query = select(PullRequest).where(PullRequest.repo_id == repo.id)
    if state != "all":
        query = query.where(PullRequest.state == state)
    if author:
        query = query.where(PullRequest.author_login.ilike(f"%{author}%"))

    query = query.order_by(PullRequest.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(query)
    prs = res.scalars().all()
    return [PullRequestResponse.model_validate(p) for p in prs]


@router.get(
    "/{repo_id}/issues",
    response_model=list[IssueResponse],
    summary="List ingested issues for a repository with optional filtering",
)
async def list_repo_issues(
    repo_id: uuid.UUID,
    state: str = Query("all", pattern="^(open|closed|all)$", description="Filter by state (open, closed, all)"),
    author: str | None = Query(None, description="Filter by author login"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IssueResponse]:
    """Retrieve issues for a repository owned by current user."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    query = select(Issue).where(Issue.repo_id == repo.id)
    if state != "all":
        query = query.where(Issue.state == state)
    if author:
        query = query.where(Issue.author_login.ilike(f"%{author}%"))

    query = query.order_by(Issue.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(query)
    issues = res.scalars().all()
    return [IssueResponse.model_validate(i) for i in issues]
