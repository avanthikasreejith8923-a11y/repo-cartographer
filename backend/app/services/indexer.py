"""Repository indexing pipeline: fetches source files, chunks content with AST/sliding-window,

generates vector embeddings, and stores files and code chunks with incremental updates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.code_chunk import CodeChunk
from app.models.index_job import IndexJob
from app.models.repo_file import RepoFile
from app.models.repository import Repository
from app.models.user import User
from app.services.chunker import chunk_file
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.repo_fetcher import (
    FetchedFile,
    fetch_repository_files,
    resolve_branch_head_sha,
)


class IndexingError(Exception):
    """Exception raised when repository indexing fails."""


def _file_priority(path: str) -> int:
    """Sort source files first (0), docs second (1), other configs/data last (2)."""
    p_lower = path.lower()
    source_exts = (
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
        ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".m", ".sh", ".bash", ".zsh", ".sql", ".html", ".css",
    )
    if any(p_lower.endswith(ext) for ext in source_exts):
        return 0
    doc_exts = (".md", ".markdown", ".rst", ".txt", ".adoc")
    if any(p_lower.endswith(ext) for ext in doc_exts) or "readme" in p_lower:
        return 1
    return 2


def _to_float_list(val: Any) -> list[float]:
    """Ensure embedding value is a list of floats (handling string representation from pgvector)."""
    if val is None:
        return [0.0] * settings.EMBEDDING_DIM
    if isinstance(val, str):
        cleaned = val.strip("[] \t\n\r")
        if not cleaned:
            return [0.0] * settings.EMBEDDING_DIM
        return [float(x) for x in cleaned.split(",")]
    if hasattr(val, "tolist"):
        return [float(x) for x in val.tolist()]
    return [float(x) for x in val]


def _get_sample_repo_files() -> list[FetchedFile]:
    """Sample files for demo mode and offline testing."""
    sample_py = '''"""FastAPI application entrypoint."""
import uvicorn
from fastapi import FastAPI, Depends

app = FastAPI(title="RepoCartographer API")

@app.get("/health")
async def health_check():
    """Return health status."""
    return {"status": "healthy"}

class SearchService:
    """Service for searching code chunks."""
    def __init__(self, model_name: str):
        self.model_name = model_name

    def search(self, query: str, limit: int = 10):
        """Execute hybrid search."""
        return []
'''
    sample_md = """# Repo Cartographer

Repo Cartographer is an AI developer productivity tool that indexes GitHub repositories.

## Features
- Ingestion of commits, PRs, and issues
- AST-based chunking for Python and sliding-window chunking
- Google Gemini vector embeddings and PostgreSQL pgvector hybrid search
- Citations with exact GitHub permalinks

## Getting Started
Run the backend server and frontend development server.
"""
    sample_ts = """// Frontend search client
export interface SearchResult {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  content: string;
  score: number;
}

export async function searchCodebase(query: string): Promise<SearchResult[]> {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  return res.json();
}
"""
    import hashlib

    def _make(path: str, content: str, lang: str) -> FetchedFile:
        return FetchedFile(
            path=path,
            content=content,
            size_bytes=len(content.encode("utf-8")),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            language=lang,
        )

    return [
        _make("backend/app/main.py", sample_py, "python"),
        _make("README.md", sample_md, "markdown"),
        _make("frontend/src/api.ts", sample_ts, "typescript"),
    ]


async def execute_repo_indexing(
    repo_id: str | uuid.UUID,
    db: AsyncSession,
    job_id: str | uuid.UUID | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> IndexJob:
    """Execute complete codebase indexing pipeline for a repository."""
    if isinstance(repo_id, str):
        repo_id = uuid.UUID(repo_id)
    if isinstance(job_id, str):
        job_id = uuid.UUID(job_id)

    # 1. Fetch Repository and User
    repo = await db.get(Repository, repo_id)
    if not repo:
        logger.info(f"Repository {repo_id} no longer exists in database; skipping indexing job.")
        return None  # type: ignore[return-value]

    user = await db.get(User, repo.user_id)
    if not user:
        raise IndexingError(f"Owner user {repo.user_id} not found for repo {repo_id}.")

    # 2. Get or create IndexJob
    job: IndexJob | None = None
    if job_id:
        job = await db.get(IndexJob, job_id)

    if not job:
        active_job_stmt = (
            select(IndexJob)
            .where(
                IndexJob.repo_id == repo.id,
                IndexJob.status.in_(["pending", "running"]),
            )
            .order_by(IndexJob.created_at.desc())
        )
        active_job_res = await db.execute(active_job_stmt)
        job = active_job_res.scalars().first()

    if not job:
        job = IndexJob(
            id=job_id or uuid.uuid4(),
            repo_id=repo.id,
            status="running",
            stage="queued",
            progress=0,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.flush()

    provider = embedding_provider or get_embedding_provider()

    try:
        # Mark running and update repo status in same transaction
        job.status = "running"
        job.stage = "fetching"
        job.progress = 10
        repo.index_status = "indexing"
        await db.commit()
        if hasattr(db, "refresh"):
            await db.refresh(repo)
            await db.refresh(job)

        # Check demo or mock mode
        is_demo_or_mock = settings.DEMO_MODE or not user.encrypted_access_token
        if not is_demo_or_mock and user.encrypted_access_token:
            if user.encrypted_access_token.startswith("ghp_demo"):
                is_demo_or_mock = True
            else:
                try:
                    from app.core.security import decrypt_token

                    raw_token = decrypt_token(user.encrypted_access_token)
                    if raw_token.startswith("ghp_demo"):
                        is_demo_or_mock = True
                except Exception:
                    pass

        # Target commit SHA
        target_commit_sha = repo.default_branch or "main"
        if not is_demo_or_mock:
            try:
                resolved_sha = await resolve_branch_head_sha(
                    full_name=repo.full_name,
                    branch=target_commit_sha,
                    encrypted_token=user.encrypted_access_token,
                )
                if resolved_sha:
                    target_commit_sha = resolved_sha
            except Exception as e:
                logger.warning(f"Could not resolve branch head sha ({e}), using '{target_commit_sha}'")

        # Stage 1: Fetching
        fetched_files: list[FetchedFile] = []
        if is_demo_or_mock:
            fetched_files = _get_sample_repo_files()
            logger.info(f"Using sample files for repo {repo.full_name} in demo/mock mode.")
        else:
            try:
                fetched_files = await fetch_repository_files(
                    full_name=repo.full_name,
                    commit_sha=target_commit_sha,
                    encrypted_token=user.encrypted_access_token,
                )
            except Exception as exc:
                # If GitHub rate limit was hit but repo is already indexed in DB, reuse existing files
                existing_files_stmt = select(RepoFile).where(RepoFile.repo_id == repo.id)
                existing_files_res = await db.execute(existing_files_stmt)
                existing_list = list(existing_files_res.scalars().all())
                if existing_list:
                    logger.warning(
                        f"GitHub fetch failed ({exc}); reusing {len(existing_list)} existing indexed files from DB."
                    )
                    fetched_files = [
                        FetchedFile(
                            path=rf.path,
                            content="",
                            language=rf.language,
                            size_bytes=rf.size_bytes or 0,
                            content_hash=rf.content_hash,
                        )
                        for rf in existing_list
                    ]
                else:
                    raise

        # Stage 2: Filtering
        job.stage = "filtering"
        job.progress = 25
        await db.commit()

        total_files = len(fetched_files)
        fetched_by_path = {f.path: f for f in fetched_files}

        # Stage 3: Chunking & Incremental Diffing
        job.stage = "chunking"
        job.progress = 40
        await db.commit()

        # Load existing indexed files
        existing_files_stmt = select(RepoFile).where(RepoFile.repo_id == repo.id)
        existing_files_res = await db.execute(existing_files_stmt)
        existing_files = {rf.path: rf for rf in existing_files_res.scalars().all()}

        new_paths: set[str] = set()
        modified_paths: set[str] = set()
        unchanged_paths: set[str] = set()
        deleted_paths: set[str] = set(existing_files.keys()) - set(fetched_by_path.keys())

        for path, f_item in fetched_by_path.items():
            if path not in existing_files:
                new_paths.add(path)
            elif existing_files[path].content_hash != f_item.content_hash:
                modified_paths.add(path)
            else:
                unchanged_paths.add(path)

        # Priority sorting: source files first, docs second, other configs/data last
        paths_to_chunk = sorted(new_paths | modified_paths, key=lambda p: (_file_priority(p), p))
        new_chunks_by_path: dict[str, list[Any]] = {}
        total_chunks_collected = 0
        truncated = False
        seen_content_hashes: set[str] = set()

        for path in paths_to_chunk:
            if total_chunks_collected >= settings.INDEX_MAX_CHUNKS:
                truncated = True
                break
            f_item = fetched_by_path[path]
            chunks = chunk_file(f_item.path, f_item.content, f_item.language)
            remaining_capacity = settings.INDEX_MAX_CHUNKS - total_chunks_collected

            # Skip duplicate chunk contents
            deduped_chunks = []
            for c in chunks:
                if c.content_hash in seen_content_hashes:
                    continue
                seen_content_hashes.add(c.content_hash)
                deduped_chunks.append(c)
                if len(deduped_chunks) >= remaining_capacity:
                    truncated = True
                    break

            new_chunks_by_path[path] = deduped_chunks
            total_chunks_collected += len(deduped_chunks)

        # Stage 4: Clean up removed paths & prepare files
        if deleted_paths:
            await db.execute(
                delete(CodeChunk).where(CodeChunk.repo_id == repo.id, CodeChunk.path.in_(deleted_paths))
            )
            await db.execute(
                delete(RepoFile).where(RepoFile.repo_id == repo.id, RepoFile.path.in_(deleted_paths))
            )

        if modified_paths:
            await db.execute(
                delete(CodeChunk).where(CodeChunk.repo_id == repo.id, CodeChunk.path.in_(modified_paths))
            )

        now = datetime.now(UTC)
        repo_files_to_save: dict[str, RepoFile] = {}
        for path in unchanged_paths:
            repo_files_to_save[path] = existing_files[path]

        for path in new_chunks_by_path:
            f_item = fetched_by_path[path]
            if path in existing_files:
                rf = existing_files[path]
                rf.content_hash = f_item.content_hash
                rf.size_bytes = f_item.size_bytes
                rf.language = f_item.language
                rf.indexed_at = now
            else:
                rf = RepoFile(
                    id=uuid.uuid4(),
                    repo_id=repo.id,
                    path=path,
                    language=f_item.language,
                    size_bytes=f_item.size_bytes,
                    content_hash=f_item.content_hash,
                    indexed_at=now,
                )
                db.add(rf)
            repo_files_to_save[path] = rf

        await db.flush()

        # Stage 5: Incremental Embedding & Immediate Saving
        job.stage = "embedding"
        job.progress = 50
        await db.commit()

        # Query existing chunks for this repo to continue where it stopped
        existing_repo_chunks_stmt = select(
            CodeChunk.path, CodeChunk.chunk_index, CodeChunk.content_hash, CodeChunk.embedding
        ).where(CodeChunk.repo_id == repo.id)
        existing_repo_chunks_res = await db.execute(existing_repo_chunks_stmt)
        existing_repo_chunks: dict[tuple[str, int], tuple[str, Any]] = {
            (row[0], row[1]): (row[2], row[3]) for row in existing_repo_chunks_res.all()
        }

        # Check existing embeddings cache across database by content_hash
        all_target_chunks: list[tuple[str, Any]] = []
        for path, chunks in new_chunks_by_path.items():
            for c in chunks:
                all_target_chunks.append((path, c))

        unique_target_hashes = list({c.content_hash for _, c in all_target_chunks})
        hash_to_embedding: dict[str, list[float]] = {}

        if unique_target_hashes:
            cached_stmt = select(CodeChunk.content_hash, CodeChunk.embedding).where(
                CodeChunk.content_hash.in_(unique_target_hashes),
                CodeChunk.embedding.is_not(None),
            )
            cached_res = await db.execute(cached_stmt)
            for row in cached_res.all():
                if row[0] not in hash_to_embedding and row[1] is not None:
                    hash_to_embedding[row[0]] = _to_float_list(row[1])

        # Chunks that truly need Gemini API calls
        chunks_to_embed: list[tuple[str, Any]] = []
        for path, c in all_target_chunks:
            existing = existing_repo_chunks.get((path, c.chunk_index))
            if existing and existing[0] == c.content_hash and existing[1] is not None:
                hash_to_embedding[c.content_hash] = _to_float_list(existing[1])
                continue
            if c.content_hash not in hash_to_embedding:
                chunks_to_embed.append((path, c))

        total_chunks_to_index = len(all_target_chunks)
        total_needing_embed = len(chunks_to_embed)
        logger.info(
            f"Codebase indexing for {repo.full_name}: {total_chunks_to_index} target chunks, "
            f"{total_needing_embed} chunks requiring new Gemini embeddings."
        )

        # Save any chunks whose embeddings are already cached
        for path, c in all_target_chunks:
            if (path, c.chunk_index) not in existing_repo_chunks and c.content_hash in hash_to_embedding:
                rf = repo_files_to_save[path]
                emb = hash_to_embedding[c.content_hash]
                db.add(
                    CodeChunk(
                        id=uuid.uuid4(),
                        repo_id=repo.id,
                        file_id=rf.id,
                        path=c.path,
                        chunk_index=c.chunk_index,
                        start_line=c.start_line,
                        end_line=c.end_line,
                        language=c.language,
                        kind=c.kind,
                        symbol=c.symbol,
                        content=c.content,
                        content_hash=c.content_hash,
                        embedding=emb,
                        embedding_model=settings.EMBEDDING_MODEL,
                    )
                )
        await db.commit()

        # Batch chunks to embed
        batches: list[list[tuple[str, Any]]] = []
        current_b: list[tuple[str, Any]] = []
        current_chars = 0

        for item in chunks_to_embed:
            c_len = len(item[1].embed_text)
            if current_b and (
                len(current_b) >= settings.EMBED_BATCH_SIZE
                or current_chars + c_len > settings.EMBED_MAX_CHARS_PER_REQUEST
            ):
                batches.append(current_b)
                current_b = [item]
                current_chars = c_len
            else:
                current_b.append(item)
                current_chars += c_len
        if current_b:
            batches.append(current_b)

        embedded_count = 0
        from app.services.gemini_retry import GeminiRateLimitBudgetExceeded

        try:
            for b in batches:
                batch_texts = [c.embed_text for _, c in b]
                batch_embeddings = await provider.embed_documents(batch_texts)
                for (_, c), emb in zip(b, batch_embeddings, strict=True):
                    hash_to_embedding[c.content_hash] = emb

                # Save each batch to database immediately
                for path, c in b:
                    rf = repo_files_to_save[path]
                    emb = hash_to_embedding[c.content_hash]
                    db.add(
                        CodeChunk(
                            id=uuid.uuid4(),
                            repo_id=repo.id,
                            file_id=rf.id,
                            path=c.path,
                            chunk_index=c.chunk_index,
                            start_line=c.start_line,
                            end_line=c.end_line,
                            language=c.language,
                            kind=c.kind,
                            symbol=c.symbol,
                            content=c.content,
                            content_hash=c.content_hash,
                            embedding=emb,
                            embedding_model=settings.EMBEDDING_MODEL,
                        )
                    )

                embedded_count += len(b)
                if total_needing_embed > 0:
                    job.progress = 50 + int(40 * (embedded_count / total_needing_embed))
                await db.commit()
                logger.info(
                    f"Saved batch ({embedded_count}/{total_needing_embed} embedded) for {repo.full_name} ({job.progress}%)"
                )

        except GeminiRateLimitBudgetExceeded as rle:
            total_saved_res = await db.execute(
                select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo.id)
            )
            saved_chunks = total_saved_res.scalar() or 0
            now = datetime.now(UTC)

            job.status = "failed"
            job.stage = "failed"
            job.finished_at = now
            if saved_chunks > 0:
                repo.index_status = "ready"
                repo.indexed_at = now
                repo.chunk_count = saved_chunks
                repo.indexed_commit_sha = target_commit_sha
                job.error = (
                    f"Gemini rate limit reached. {saved_chunks} of {total_chunks_to_index} chunks were saved. "
                    "Click Index again to continue."
                )
                job.stats = {
                    "partial": True,
                    "saved_chunks": saved_chunks,
                    "total_chunks": total_chunks_to_index,
                }
            else:
                repo.index_status = "failed"
                job.error = "Gemini rate limit reached. 0 chunks were saved. Click Index again to retry."
                job.stats = {"partial": False, "saved_chunks": 0, "total_chunks": total_chunks_to_index}

            await db.commit()
            if hasattr(db, "refresh"):
                await db.refresh(repo)
                await db.refresh(job)
            logger.warning(f"Indexing interrupted by rate limit for {repo.full_name}: {job.error} ({rle})")
            return job

        # Total chunk count
        total_chunks_res = await db.execute(
            select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo.id)
        )
        total_chunks = total_chunks_res.scalar() or 0

        if total_chunks == 0:
            raise IndexingError(
                f"Repository indexing produced 0 code chunks for {repo.full_name}. "
                "Ensure repository contains supported, non-empty source files."
            )

        # Complete Repository & Job in the SAME transaction
        repo.index_status = "ready"
        repo.indexed_commit_sha = target_commit_sha
        repo.indexed_at = now
        repo.chunk_count = total_chunks

        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.finished_at = now
        job.error = None
        job.stats = {
            "total_files": total_files,
            "new_files": len(new_paths),
            "modified_files": len(modified_paths),
            "unchanged_files": len(unchanged_paths),
            "deleted_files": len(deleted_paths),
            "total_chunks": total_chunks,
            "new_chunks": embedded_count,
            "truncated": truncated,
            "partial": False,
        }

        await db.commit()
        if hasattr(db, "refresh"):
            await db.refresh(repo)
            await db.refresh(job)

        logger.info(
            f"Successfully indexed repo {repo.full_name}: {total_files} files, {total_chunks} total chunks."
        )
        return job

    except Exception as exc:
        repo_id_val = repo.id if repo else repo_id
        job_id_val = job.id if job else job_id
        await db.rollback()
        error_msg = str(exc)[:500]
        logger.error(f"Failed to index repo {repo_id}: {error_msg}")

        # Reload fresh instances cleanly
        repo = await db.get(Repository, repo_id_val)
        job = await db.get(IndexJob, job_id_val) if job_id_val else None

        # Check if partial chunks exist
        total_saved_res = await db.execute(
            select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo_id_val)
        )
        saved_chunks = total_saved_res.scalar() or 0
        now = datetime.now(UTC)

        if job:
            job.status = "failed"
            job.stage = "failed"
            job.error = error_msg
            job.finished_at = now
            if saved_chunks > 0:
                job.stats = {"partial": True, "saved_chunks": saved_chunks}
            else:
                job.stats = {"partial": False, "saved_chunks": 0}
            db.add(job)

        if repo:
            if saved_chunks > 0:
                repo.index_status = "ready"
                repo.chunk_count = saved_chunks
                repo.indexed_at = now
            else:
                repo.index_status = "failed"
            db.add(repo)

        await db.commit()
        if hasattr(db, "refresh"):
            if repo:
                await db.refresh(repo)
            if job:
                await db.refresh(job)
        return job
