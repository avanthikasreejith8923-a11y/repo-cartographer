"""API routes for repository discovery, import, and management."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis import asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db, get_redis
from app.models.analysis_job import AnalysisJob
from app.models.commit import Commit
from app.models.generated_test import GeneratedTest
from app.models.index_job import IndexJob
from app.models.issue import Issue
from app.models.issue_analysis import IssueAnalysis
from app.models.pr_analysis import PRAnalysis
from app.models.pull_request import PullRequest
from app.models.qa_history import QAHistory
from app.models.repo_doc import RepoDoc
from app.models.repo_file import RepoFile
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.user import User
from app.schemas.intelligence import (
    AnalysisJobResponse,
    DuplicateIssuePair,
    GeneratedTestResponse,
    GenerateTestRequest,
    IssueAnalysisResponse,
    PRAnalysisResponse,
)
from app.schemas.repository import (
    AskQuestionRequest,
    AskQuestionResponse,
    AvailableRepoResponse,
    CodeSearchRequest,
    CommitResponse,
    DocResponse,
    IndexJobResponse,
    IssueResponse,
    PullRequestResponse,
    QAHistoryResponse,
    RepoImportRequest,
    RepoImportResponse,
    RepoResponse,
    SearchResultResponse,
    SourceCitationResponse,
    SyncJobResponse,
)
from app.services.github_client import GitHubAPIError, GitHubClient
from app.services.issue_analysis import find_duplicate_issues
from app.services.pr_analysis import analyze_pull_request
from app.services.qa import ask_codebase
from app.services.queue import (
    check_and_expire_stuck_doc_job,
    check_and_expire_stuck_index_job,
    check_and_expire_stuck_issue_job,
    check_and_expire_stuck_sync_job,
    enqueue_doc_job,
    enqueue_index_job,
    enqueue_issue_analysis_job,
    enqueue_sync_job,
    reconcile_repository_status,
)
from app.services.search import execute_code_search
from app.services.test_generation import generate_test_for_file

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
    redis: aioredis.Redis = Depends(get_redis),
) -> list[RepoResponse]:
    """Retrieve all repositories belonging to the authenticated user."""
    stmt = (
        select(Repository)
        .where(Repository.user_id == current_user.id)
        .order_by(Repository.created_at.desc())
    )
    result = await db.execute(stmt)
    repos = result.scalars().all()
    reconciled_any = False
    for r in repos:
        changed = await reconcile_repository_status(r, db, redis)
        if changed:
            reconciled_any = True
    if reconciled_any:
        fresh_res = await db.execute(stmt)
        repos = fresh_res.scalars().all()
    else:
        for r in repos:
            if hasattr(db, "refresh"):
                await db.refresh(r)
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
    redis: aioredis.Redis = Depends(get_redis),
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
    await reconcile_repository_status(repo, db, redis)
    if hasattr(db, "refresh"):
        await db.refresh(repo)
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
    redis: aioredis.Redis = Depends(get_redis),
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

    # Check if a sync job is already active (pending or running, not expired)
    active_job_stmt = (
        select(SyncJob)
        .where(
            SyncJob.repo_id == repo.id,
            SyncJob.status.in_(["pending", "running"]),
        )
        .order_by(SyncJob.created_at.desc())
    )
    active_job_res = await db.execute(active_job_stmt)
    active_job = active_job_res.scalars().first()
    if active_job is not None:
        was_expired = await check_and_expire_stuck_sync_job(active_job, repo, db, redis)
        if was_expired:
            active_job = None

    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository synchronization is already pending or running",
        )

    now = datetime.now(UTC)
    repo.status = "pending"
    repo.sync_error = None
    if hasattr(repo, "updated_at"):
        repo.updated_at = now

    sync_job = SyncJob(
        repo_id=repo.id,
        status="pending",
        stage="queued",
        progress=0,
        started_at=now,
    )
    if hasattr(sync_job, "updated_at"):
        sync_job.updated_at = now

    db.add(sync_job)
    db.add(repo)
    await db.commit()
    await db.refresh(sync_job)
    await db.refresh(repo)

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
    redis: aioredis.Redis = Depends(get_redis),
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

    await check_and_expire_stuck_sync_job(sync_job, repo, db, redis)
    await reconcile_repository_status(repo, db, redis)
    if hasattr(db, "refresh"):
        await db.refresh(sync_job)
        await db.refresh(repo)

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


@router.post(
    "/{repo_id}/index",
    response_model=IndexJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger codebase indexing for a repository",
)
async def trigger_repo_indexing(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> IndexJobResponse:
    """Enqueues a background indexing task for the specified repository."""
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

    active_index_job_stmt = (
        select(IndexJob)
        .where(
            IndexJob.repo_id == repo.id,
            IndexJob.status.in_(["pending", "running"]),
        )
        .order_by(IndexJob.created_at.desc())
    )
    active_index_job_res = await db.execute(active_index_job_stmt)
    active_index_job = active_index_job_res.scalars().first()
    if active_index_job is not None:
        was_expired = await check_and_expire_stuck_index_job(active_index_job, repo, db, redis)
        if was_expired:
            active_index_job = None

    if active_index_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository is currently being indexed",
        )

    now = datetime.now(UTC)
    job = IndexJob(
        id=uuid.uuid4(),
        repo_id=repo.id,
        status="running",
        stage="queued",
        progress=0,
        stats={},
        started_at=now,
    )
    if hasattr(job, "updated_at"):
        job.updated_at = now
    repo.index_status = "indexing"
    if hasattr(repo, "updated_at"):
        repo.updated_at = now

    db.add(job)
    db.add(repo)
    await db.commit()
    await db.refresh(job)
    await db.refresh(repo)

    await enqueue_index_job(repo.id, job.id)
    return IndexJobResponse.model_validate(job)


@router.get(
    "/{repo_id}/index-status",
    response_model=IndexJobResponse,
    summary="Get latest codebase indexing status for a repository",
)
async def get_repo_indexing_status(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> IndexJobResponse:
    """Returns the latest indexing job status for the specified repository."""
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
        select(IndexJob)
        .where(IndexJob.repo_id == repo.id)
        .order_by(IndexJob.created_at.desc())
    )
    job_res = await db.execute(job_stmt)
    index_job = job_res.scalars().first()
    if not index_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No indexing job found for repository",
        )

    await check_and_expire_stuck_index_job(index_job, repo, db, redis)
    await reconcile_repository_status(repo, db, redis)
    if hasattr(db, "refresh"):
        await db.refresh(index_job)
        await db.refresh(repo)

    return IndexJobResponse.model_validate(index_job)



@router.post(
    "/{repo_id}/search",
    response_model=list[SearchResultResponse],
    summary="Search codebase using hybrid, semantic, or keyword search",
)
async def search_repo_codebase(
    repo_id: uuid.UUID,
    search_req: CodeSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SearchResultResponse]:
    """Execute code search across indexed repository code chunks."""
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

    if repo.index_status != "ready" and (repo.chunk_count or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository codebase has not been indexed yet. Please trigger indexing before searching.",
        )

    results = await execute_code_search(
        repo=repo,
        query=search_req.query,
        mode=search_req.mode,  # type: ignore[arg-type]
        limit=search_req.limit,
        db=db,
    )

    return [
        SearchResultResponse(
            id=r.id,
            path=r.path,
            start_line=r.start_line,
            end_line=r.end_line,
            language=r.language,
            symbol=r.symbol,
            kind=r.kind,
            score=r.score,
            snippet=r.snippet,
            permalink=r.permalink,
        )
        for r in results
    ]


@router.post(
    "/{repo_id}/ask",
    response_model=AskQuestionResponse,
    summary="Ask a question about the repository codebase",
)
async def ask_repo_question(
    repo_id: uuid.UUID,
    ask_req: AskQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AskQuestionResponse:
    """Execute cited question answering grounded in codebase chunks."""
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

    if repo.index_status != "ready" and (repo.chunk_count or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository codebase has not been indexed yet. Please trigger indexing before asking questions.",
        )

    result = await ask_codebase(
        repo=repo,
        user=current_user,
        question=ask_req.question,
        db=db,
        redis_client=redis,
    )

    return AskQuestionResponse(
        answer=result.answer,
        status=result.status,
        citations_missing=result.citations_missing,
        sources=[
            SourceCitationResponse(
                marker=s["marker"],
                path=s["path"],
                start_line=s["start_line"],
                end_line=s["end_line"],
                symbol=s.get("symbol"),
                language=s.get("language"),
                snippet=s["snippet"],
                permalink=s["permalink"],
            )
            for s in result.sources
        ],
        history_id=result.history_id,
        latency_ms=result.latency_ms,
    )


@router.get(
    "/{repo_id}/ask/history",
    response_model=list[QAHistoryResponse],
    summary="List question answering history for repository",
)
async def list_repo_qa_history(
    repo_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100, description="Max history items"),
    offset: int = Query(0, ge=0, description="Offset items"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QAHistoryResponse]:
    """Retrieve historical question-answering sessions for repository."""
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

    hist_stmt = (
        select(QAHistory)
        .where(
            QAHistory.repo_id == repo.id,
            QAHistory.user_id == current_user.id,
        )
        .order_by(QAHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    hist_res = await db.execute(hist_stmt)
    records = hist_res.scalars().all()
    return [QAHistoryResponse.model_validate(r) for r in records]


@router.delete(
    "/{repo_id}/ask/history/{history_id}",
    summary="Delete a question answering history entry",
)
async def delete_repo_qa_history(
    repo_id: uuid.UUID,
    history_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Delete an individual question answering history record."""
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

    hist_stmt = select(QAHistory).where(
        QAHistory.id == history_id,
        QAHistory.repo_id == repo.id,
        QAHistory.user_id == current_user.id,
    )
    hist_res = await db.execute(hist_stmt)
    hist = hist_res.scalar_one_or_none()
    if not hist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="History entry not found",
        )

    await db.delete(hist)
    await db.commit()
    return {"deleted": True}


@router.post(
    "/{repo_id}/docs/{doc_type}/generate",
    response_model=DocResponse,
    summary="Trigger asynchronous documentation generation",
)
async def generate_repo_doc(
    repo_id: uuid.UUID,
    doc_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DocResponse:
    """Queue background documentation generation job for Architecture or README."""
    norm_doc_type = doc_type.lower().strip()
    if norm_doc_type not in ("architecture", "readme"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid doc_type: {doc_type}. Must be 'architecture' or 'readme'.",
        )

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

    if repo.index_status != "ready" and (repo.chunk_count or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository codebase has not been indexed yet. Please trigger indexing before generating documentation.",
        )

    doc_stmt = select(RepoDoc).where(
        RepoDoc.repo_id == repo.id,
        RepoDoc.doc_type == norm_doc_type,
    )
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()

    if doc and doc.status in ("pending", "generating"):
        was_expired = await check_and_expire_stuck_doc_job(doc, db, redis)
        if not was_expired and doc.status in ("pending", "generating"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Documentation generation is already in progress.",
            )

    now = datetime.now(UTC)
    if not doc:
        doc = RepoDoc(
            repo_id=repo.id,
            doc_type=norm_doc_type,
            status="pending",
            content_markdown=None,
            citations=[],
            error=None,
            model=None,
            indexed_commit_sha=repo.indexed_commit_sha,
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
    else:
        doc.status = "pending"
        doc.error = None
        doc.updated_at = now

    await db.commit()
    await db.refresh(doc)

    await enqueue_doc_job(repo.id, norm_doc_type)

    return DocResponse.model_validate(doc)


@router.get(
    "/{repo_id}/docs/{doc_type}",
    response_model=DocResponse,
    summary="Get generated documentation for repository",
)
async def get_repo_doc(
    repo_id: uuid.UUID,
    doc_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DocResponse:
    """Retrieve the generated Architecture or README documentation."""
    norm_doc_type = doc_type.lower().strip()
    if norm_doc_type not in ("architecture", "readme"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid doc_type: {doc_type}. Must be 'architecture' or 'readme'.",
        )

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

    doc_stmt = select(RepoDoc).where(
        RepoDoc.repo_id == repo.id,
        RepoDoc.doc_type == norm_doc_type,
    )
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()

    if doc and doc.status in ("pending", "generating"):
        await check_and_expire_stuck_doc_job(doc, db, redis)
        if hasattr(db, "refresh"):
            await db.refresh(doc)
            await db.refresh(repo)

    if not doc:
        return DocResponse(
            repo_id=repo.id,
            doc_type=norm_doc_type,
            status="not_started",
            content_markdown=None,
            citations=[],
            is_stale=False,
        )

    is_stale = bool(
        repo.indexed_commit_sha
        and doc.indexed_commit_sha
        and doc.indexed_commit_sha != repo.indexed_commit_sha
    )

    doc_resp = DocResponse.model_validate(doc)
    doc_resp.is_stale = is_stale
    return doc_resp


@router.post(
    "/{repo_id}/pulls/{number}/analyze",
    response_model=PRAnalysisResponse,
    summary="Analyze pull request and generate summary with risk assessment",
)
async def analyze_repo_pull_request(
    repo_id: uuid.UUID,
    number: int,
    refresh: bool = Query(default=False, description="Force re-analysis even if already analyzed"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> PRAnalysisResponse:
    """Analyze a pull request for risk factors and generate AI review summary."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    analysis = await analyze_pull_request(
        repo=repo,
        pr_number=number,
        user=current_user,
        db=db,
        redis_client=redis,
        refresh=refresh,
    )
    return PRAnalysisResponse.model_validate(analysis)


@router.get(
    "/{repo_id}/pulls/{number}/analysis",
    response_model=PRAnalysisResponse,
    summary="Get analysis for a specific pull request",
)
async def get_pull_request_analysis(
    repo_id: uuid.UUID,
    number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PRAnalysisResponse:
    """Retrieve existing analysis and risk score for a specific pull request."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = select(PRAnalysis).where(
        PRAnalysis.repo_id == repo.id,
        PRAnalysis.pr_number == number,
    )
    result = await db.execute(stmt)
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for PR #{number}.",
        )

    return PRAnalysisResponse.model_validate(analysis)


@router.get(
    "/{repo_id}/pulls/analyses",
    response_model=list[PRAnalysisResponse],
    summary="List all pull request analyses for repository",
)
async def list_pull_request_analyses(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PRAnalysisResponse]:
    """Retrieve all PR analyses for a repository, ordered by newest first."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = (
        select(PRAnalysis)
        .where(PRAnalysis.repo_id == repo.id)
        .order_by(PRAnalysis.created_at.desc())
    )
    result = await db.execute(stmt)
    analyses = result.scalars().all()
    return [PRAnalysisResponse.model_validate(a) for a in analyses]


@router.post(
    "/{repo_id}/issues/analyze",
    response_model=AnalysisJobResponse,
    summary="Trigger asynchronous issue classification and duplicate analysis job",
)
async def trigger_issue_analysis(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AnalysisJobResponse:
    """Start background classification and embedding for repository issues."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    # Check if repo has synced issues
    count_stmt = select(func.count(Issue.id)).where(Issue.repo_id == repo.id)
    count_res = await db.execute(count_stmt)
    issue_count = count_res.scalar() or 0
    if issue_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository has no synced issues to analyze. Please sync repository first.",
        )

    # Check for already running job
    job_stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.repo_id == repo.id, AnalysisJob.kind == "issues")
        .order_by(AnalysisJob.created_at.desc())
    )
    job_res = await db.execute(job_stmt)
    existing_job = job_res.scalars().first()

    if existing_job:
        await check_and_expire_stuck_issue_job(existing_job, db, redis)
        if existing_job.status in ("pending", "running"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Issue analysis job is already running.",
            )

    now = datetime.now(UTC)
    new_job = AnalysisJob(
        repo_id=repo.id,
        kind="issues",
        status="pending",
        stage="queued",
        progress=0,
        started_at=now,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)

    await enqueue_issue_analysis_job(repo.id)
    return AnalysisJobResponse.model_validate(new_job)


@router.get(
    "/{repo_id}/issues/analysis-status",
    response_model=AnalysisJobResponse,
    summary="Get status of issue analysis job",
)
async def get_issue_analysis_status(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AnalysisJobResponse:
    """Retrieve current progress and state of issue classification job."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    job_stmt = (
        select(AnalysisJob)
        .where(AnalysisJob.repo_id == repo.id, AnalysisJob.kind == "issues")
        .order_by(AnalysisJob.created_at.desc())
    )
    job_res = await db.execute(job_stmt)
    job = job_res.scalars().first()

    if job and job.status in ("pending", "running"):
        await check_and_expire_stuck_issue_job(job, db, redis)
        if hasattr(db, "refresh"):
            await db.refresh(job)
            await db.refresh(repo)

    if not job:
        return AnalysisJobResponse(
            id=uuid.uuid4(),
            repo_id=repo.id,
            kind="issues",
            status="none",
            stage="none",
            progress=0,
            error=None,
            stats=None,
            started_at=None,
            finished_at=None,
        )

    return AnalysisJobResponse.model_validate(job)


@router.get(
    "/{repo_id}/issues/analysis",
    response_model=list[IssueAnalysisResponse],
    summary="List classified issues with pagination and optional type filter",
)
async def list_issue_analyses(
    repo_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    type: str | None = Query(default=None, description="Filter by issue_type (bug, feature, etc.)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IssueAnalysisResponse]:
    """Retrieve paginated issue classification records."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = select(IssueAnalysis).where(IssueAnalysis.repo_id == repo.id)
    if type:
        stmt = stmt.where(IssueAnalysis.issue_type == type.lower().strip())

    offset = (page - 1) * limit
    stmt = stmt.order_by(IssueAnalysis.analyzed_at.desc()).offset(offset).limit(limit)

    res = await db.execute(stmt)
    items = res.scalars().all()
    return [IssueAnalysisResponse.model_validate(item) for item in items]


@router.get(
    "/{repo_id}/issues/duplicates",
    response_model=list[DuplicateIssuePair],
    summary="Find duplicate issue pairs using pgvector cosine similarity",
)
async def get_duplicate_issues(
    repo_id: uuid.UUID,
    threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DuplicateIssuePair]:
    """Calculate and return possible duplicate issues based on cosine similarity."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    return await find_duplicate_issues(repo, db, threshold=threshold, limit=limit)


@router.get(
    "/{repo_id}/files",
    response_model=list[str],
    summary="List indexed repository file paths for file picker",
)
async def list_repo_files(
    repo_id: uuid.UUID,
    q: str = Query(default="", description="Optional search term to filter file paths"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    """List indexed file paths from repo_files for the file picker."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = select(RepoFile.path).where(RepoFile.repo_id == repo.id)
    if q and q.strip():
        stmt = stmt.where(RepoFile.path.ilike(f"%{q.strip()}%"))

    stmt = stmt.order_by(RepoFile.path.asc()).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/{repo_id}/tests/generate",
    response_model=GeneratedTestResponse,
    summary="Generate unit test draft for a repository source file",
)
async def generate_file_tests(
    repo_id: uuid.UUID,
    request: GenerateTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> GeneratedTestResponse:
    """Generate unit test draft for a specific indexed source file."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    test_record = await generate_test_for_file(
        repo=repo,
        user=current_user,
        path=request.path.strip(),
        db=db,
        redis_client=redis,
    )
    return GeneratedTestResponse.model_validate(test_record)


@router.get(
    "/{repo_id}/tests",
    response_model=list[GeneratedTestResponse],
    summary="List generated test draft history for repository",
)
async def list_generated_tests(
    repo_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GeneratedTestResponse]:
    """Retrieve history of generated test drafts for repository."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = (
        select(GeneratedTest)
        .where(GeneratedTest.repo_id == repo.id)
        .order_by(GeneratedTest.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    items = res.scalars().all()
    return [GeneratedTestResponse.model_validate(item) for item in items]


@router.delete(
    "/{repo_id}/tests/{test_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a generated test draft",
)
async def delete_generated_test(
    repo_id: uuid.UUID,
    test_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a generated test draft by ID."""
    repo_stmt = select(Repository).where(
        Repository.id == repo_id,
        Repository.user_id == current_user.id,
    )
    repo_res = await db.execute(repo_stmt)
    repo = repo_res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    stmt = select(GeneratedTest).where(
        GeneratedTest.id == test_id,
        GeneratedTest.repo_id == repo.id,
    )
    res = await db.execute(stmt)
    test_record = res.scalar_one_or_none()
    if not test_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated test not found.",
        )

    await db.delete(test_record)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

