"""Hybrid code search service combining pgvector cosine semantic search and PostgreSQL full-text search via Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.services.embeddings import EmbeddingProvider, get_embedding_provider

SearchMode = Literal["hybrid", "semantic", "keyword"]


@dataclass(frozen=True)
class SearchResultItem:
    """Represents a ranked code search result with deep-link metadata."""

    id: uuid.UUID
    path: str
    start_line: int
    end_line: int
    language: str | None
    symbol: str | None
    kind: str
    score: float
    snippet: str
    permalink: str


def reciprocal_rank_fusion(
    semantic_ids: list[uuid.UUID],
    keyword_ids: list[uuid.UUID],
    k: int = 60,
) -> list[tuple[uuid.UUID, float]]:
    """Compute Reciprocal Rank Fusion (RRF) scores across ranked lists.

    Formula: score(d) = sum(1 / (k + rank_i)) for rank_i (1-based) across lists.
    """
    scores: dict[uuid.UUID, float] = {}

    for rank, chunk_id in enumerate(semantic_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

    for rank, chunk_id in enumerate(keyword_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked


def build_github_permalink(
    full_name: str,
    commit_sha: str | None,
    path: str,
    start_line: int,
    end_line: int,
) -> str:
    """Construct deep-linked GitHub blob permalink to exact lines."""
    sha = commit_sha or "main"
    norm_path = path.lstrip("/")
    if start_line == end_line:
        return f"https://github.com/{full_name}/blob/{sha}/{norm_path}#L{start_line}"
    return f"https://github.com/{full_name}/blob/{sha}/{norm_path}#L{start_line}-L{end_line}"


async def search_semantic(
    repo_id: uuid.UUID,
    query_vector: list[float],
    limit: int,
    db: AsyncSession,
) -> list[tuple[CodeChunk, float]]:
    """Execute cosine distance vector search against code_chunks using pgvector."""
    # Cosine distance: 0 = identical, 2 = opposite. Similarity = 1 - distance
    dist_expr = CodeChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        sa.select(CodeChunk, dist_expr)
        .where(CodeChunk.repo_id == repo_id)
        .order_by(dist_expr.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items: list[tuple[CodeChunk, float]] = []
    for chunk, dist in result.all():
        sim_score = max(0.0, 1.0 - float(dist)) if dist is not None else 0.0
        items.append((chunk, sim_score))
    return items


async def search_keyword(
    repo_id: uuid.UUID,
    query_text: str,
    limit: int,
    db: AsyncSession,
) -> list[tuple[CodeChunk, float]]:
    """Execute full-text keyword search against code_chunks tsv column using PostgreSQL plainto_tsquery."""
    ts_query = sa.func.plainto_tsquery("simple", query_text)
    rank_expr = sa.func.ts_rank_cd(CodeChunk.tsv, ts_query).label("rank")
    stmt = (
        sa.select(CodeChunk, rank_expr)
        .where(CodeChunk.repo_id == repo_id, CodeChunk.tsv.op("@@")(ts_query))
        .order_by(rank_expr.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items: list[tuple[CodeChunk, float]] = []
    for chunk, rank in result.all():
        score = float(rank) if rank is not None else 0.0
        items.append((chunk, score))
    return items


async def execute_code_search(
    repo: Repository,
    query: str,
    mode: SearchMode = "hybrid",
    limit: int = 10,
    db: AsyncSession | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[SearchResultItem]:
    """Execute code search (hybrid, semantic, or keyword) for a repository."""
    if not db:
        raise ValueError("Database session is required for code search.")

    limit = max(1, min(limit, 50))
    provider = embedding_provider or get_embedding_provider()

    results: list[SearchResultItem] = []

    if mode == "semantic":
        query_vector = await provider.embed_query(query)
        semantic_items = await search_semantic(repo.id, query_vector, limit, db)
        for chunk, score in semantic_items:
            results.append(
                SearchResultItem(
                    id=chunk.id,
                    path=chunk.path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    language=chunk.language,
                    symbol=chunk.symbol,
                    kind=chunk.kind,
                    score=score,
                    snippet=chunk.content,
                    permalink=build_github_permalink(
                        repo.full_name, repo.indexed_commit_sha, chunk.path, chunk.start_line, chunk.end_line
                    ),
                )
            )
        return results

    if mode == "keyword":
        keyword_items = await search_keyword(repo.id, query, limit, db)
        for chunk, score in keyword_items:
            results.append(
                SearchResultItem(
                    id=chunk.id,
                    path=chunk.path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    language=chunk.language,
                    symbol=chunk.symbol,
                    kind=chunk.kind,
                    score=score,
                    snippet=chunk.content,
                    permalink=build_github_permalink(
                        repo.full_name, repo.indexed_commit_sha, chunk.path, chunk.start_line, chunk.end_line
                    ),
                )
            )
        return results

    # Hybrid Search: Retrieve top 30 from both channels, fuse with RRF (k=60)
    CANDIDATE_POOL = 30
    query_vector = await provider.embed_query(query)
    semantic_items = await search_semantic(repo.id, query_vector, CANDIDATE_POOL, db)
    keyword_items = await search_keyword(repo.id, query, CANDIDATE_POOL, db)

    chunk_map: dict[uuid.UUID, CodeChunk] = {}
    for c, _ in semantic_items:
        chunk_map[c.id] = c
    for c, _ in keyword_items:
        chunk_map[c.id] = c

    semantic_ids = [c.id for c, _ in semantic_items]
    keyword_ids = [c.id for c, _ in keyword_items]

    rrf_ranked = reciprocal_rank_fusion(semantic_ids, keyword_ids, k=60)

    for chunk_id, rrf_score in rrf_ranked[:limit]:
        chunk = chunk_map[chunk_id]
        results.append(
            SearchResultItem(
                id=chunk.id,
                path=chunk.path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                language=chunk.language,
                symbol=chunk.symbol,
                kind=chunk.kind,
                score=rrf_score,
                snippet=chunk.content,
                permalink=build_github_permalink(
                    repo.full_name, repo.indexed_commit_sha, chunk.path, chunk.start_line, chunk.end_line
                ),
            )
        )

    return results
