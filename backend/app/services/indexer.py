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
        raise IndexingError(f"Repository {repo_id} not found.")

    user = await db.get(User, repo.user_id)
    if not user:
        raise IndexingError(f"Owner user {repo.user_id} not found for repo {repo_id}.")

    # 2. Get or create IndexJob
    job: IndexJob | None = None
    if job_id:
        job = await db.get(IndexJob, job_id)

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
        # Mark running
        job.status = "running"
        job.stage = "fetching"
        job.progress = 10
        repo.index_status = "indexing"
        await db.commit()

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
            resolved_sha = await resolve_branch_head_sha(
                full_name=repo.full_name,
                branch=target_commit_sha,
                encrypted_token=user.encrypted_access_token,
            )
            if resolved_sha:
                target_commit_sha = resolved_sha

        # Stage 1: Fetching
        fetched_files: list[FetchedFile] = []
        if is_demo_or_mock:
            fetched_files = _get_sample_repo_files()
            logger.info(f"Using sample files for repo {repo.full_name} in demo/mock mode.")
        else:
            fetched_files = await fetch_repository_files(
                full_name=repo.full_name,
                commit_sha=target_commit_sha,
                encrypted_token=user.encrypted_access_token,
            )

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

        # Chunk modified and new files with INDEX_MAX_CHUNKS cap
        paths_to_chunk = sorted(new_paths | modified_paths)
        new_chunks_by_path: dict[str, list[Any]] = {}
        total_chunks_collected = 0
        truncated = False

        for path in paths_to_chunk:
            if total_chunks_collected >= settings.INDEX_MAX_CHUNKS:
                truncated = True
                break
            f_item = fetched_by_path[path]
            chunks = chunk_file(f_item.path, f_item.content, f_item.language)
            remaining_capacity = settings.INDEX_MAX_CHUNKS - total_chunks_collected
            if len(chunks) > remaining_capacity:
                chunks = chunks[:remaining_capacity]
                truncated = True
            new_chunks_by_path[path] = chunks
            total_chunks_collected += len(chunks)

        # Stage 4: Embedding
        job.stage = "embedding"
        job.progress = 60
        await db.commit()

        # Flatten chunks to embed
        all_new_chunks: list[tuple[str, Any]] = []
        for path, chunks in new_chunks_by_path.items():
            for c in chunks:
                all_new_chunks.append((path, c))

        # Check existing embeddings cache by content_hash to avoid re-computing
        unique_hashes = list({c.content_hash for _, c in all_new_chunks})
        hash_to_embedding: dict[str, list[float]] = {}

        if unique_hashes:
            cached_stmt = (
                select(CodeChunk.content_hash, CodeChunk.embedding)
                .where(CodeChunk.content_hash.in_(unique_hashes))
            )
            cached_res = await db.execute(cached_stmt)
            for row in cached_res.all():
                if row[0] not in hash_to_embedding:
                    hash_to_embedding[row[0]] = _to_float_list(row[1])

        # Embed remaining uncached chunks
        texts_to_embed: list[str] = []
        hashes_to_embed: list[str] = []
        for _, c in all_new_chunks:
            if c.content_hash not in hash_to_embedding and c.content_hash not in hashes_to_embed:
                texts_to_embed.append(c.embed_text)
                hashes_to_embed.append(c.content_hash)

        if texts_to_embed:
            embeddings_list = await provider.embed_documents(texts_to_embed)
            for h, emb in zip(hashes_to_embed, embeddings_list, strict=True):
                hash_to_embedding[h] = emb

        job.progress = 80
        await db.commit()

        # Stage 5: Saving & Database Updates
        job.stage = "saving"
        job.progress = 90
        await db.commit()

        # 5a. Delete chunks and RepoFiles for deleted paths
        if deleted_paths:
            await db.execute(
                delete(CodeChunk).where(CodeChunk.repo_id == repo.id, CodeChunk.path.in_(deleted_paths))
            )
            await db.execute(
                delete(RepoFile).where(RepoFile.repo_id == repo.id, RepoFile.path.in_(deleted_paths))
            )

        # 5b. Delete old chunks for modified paths
        if modified_paths:
            await db.execute(
                delete(CodeChunk).where(CodeChunk.repo_id == repo.id, CodeChunk.path.in_(modified_paths))
            )

        # 5c. Upsert RepoFiles
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

        # 5d. Insert CodeChunks in bounded batches of 100
        chunks_to_insert: list[CodeChunk] = []
        for path, chunks in new_chunks_by_path.items():
            rf = repo_files_to_save[path]
            for c in chunks:
                emb = _to_float_list(hash_to_embedding.get(c.content_hash, [0.0] * settings.EMBEDDING_DIM))
                chunk_record = CodeChunk(
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
                chunks_to_insert.append(chunk_record)

        if chunks_to_insert:
            BATCH_SIZE = 100
            for i in range(0, len(chunks_to_insert), BATCH_SIZE):
                batch = chunks_to_insert[i : i + BATCH_SIZE]
                db.add_all(batch)
                await db.flush()

        # Total chunk count
        total_chunks_res = await db.execute(
            select(func.count(CodeChunk.id)).where(CodeChunk.repo_id == repo.id)
        )
        total_chunks = total_chunks_res.scalar() or 0

        # Complete Repository & Job
        repo.index_status = "ready"
        repo.indexed_commit_sha = target_commit_sha
        repo.indexed_at = now
        repo.chunk_count = total_chunks

        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        job.finished_at = now
        job.stats = {
            "total_files": total_files,
            "new_files": len(new_paths),
            "modified_files": len(modified_paths),
            "unchanged_files": len(unchanged_paths),
            "deleted_files": len(deleted_paths),
            "total_chunks": total_chunks,
            "new_chunks": len(chunks_to_insert),
            "truncated": truncated,
        }

        await db.commit()
        logger.info(
            f"Successfully indexed repo {repo.full_name}: {total_files} files, {total_chunks} total chunks."
        )
        return job

    except Exception as exc:
        await db.rollback()
        error_msg = str(exc)[:500]
        logger.error(f"Failed to index repo {repo_id}: {error_msg}")

        job.status = "failed"
        job.stage = "failed"
        job.error = error_msg
        job.finished_at = datetime.now(UTC)
        repo.index_status = "failed"

        db.add(job)
        db.add(repo)
        await db.commit()
        return job
