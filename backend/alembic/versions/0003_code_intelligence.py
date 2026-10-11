"""Add repo_files, code_chunks (pgvector HNSW + full-text GIN), and index_jobs tables.

Revision ID: 0003_code_intelligence
Revises: 0002_ingestion_tables
Create Date: 2026-10-04 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "0003_code_intelligence"
down_revision: str | None = "0002_ingestion_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update repositories table with indexing columns
    op.add_column("repositories", sa.Column("index_status", sa.String(length=50), nullable=False, server_default="none"))
    op.add_column("repositories", sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True))
    op.add_column("repositories", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_index(op.f("ix_repositories_index_status"), "repositories", ["index_status"], unique=False)

    # 2. repo_files table
    op.create_table(
        "repo_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "path", name="uq_repo_files_repo_path"),
    )
    op.create_index(op.f("ix_repo_files_repo_id"), "repo_files", ["repo_id"], unique=False)
    op.create_index(op.f("ix_repo_files_path"), "repo_files", ["path"], unique=False)

    # 3. code_chunks table
    op.create_table(
        "code_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repo_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(settings.EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', content)", persisted=True),
            nullable=True,
        ),
        sa.UniqueConstraint("file_id", "chunk_index", name="uq_code_chunks_file_chunk_index"),
    )
    op.create_index(op.f("ix_code_chunks_repo_id"), "code_chunks", ["repo_id"], unique=False)
    op.create_index(op.f("ix_code_chunks_file_id"), "code_chunks", ["file_id"], unique=False)
    op.create_index("ix_code_chunks_repo_path", "code_chunks", ["repo_id", "path"], unique=False)
    op.create_index(op.f("ix_code_chunks_content_hash"), "code_chunks", ["content_hash"], unique=False)

    # Vector HNSW Index (Cosine Distance) and Full-text GIN Index
    op.execute(
        "CREATE INDEX ix_code_chunks_embedding_hnsw ON code_chunks "
        "USING hnsw (embedding vector_cosine_ops);"
    )
    op.execute(
        "CREATE INDEX ix_code_chunks_tsv ON code_chunks "
        "USING gin (tsv);"
    )

    # 4. index_jobs table
    op.create_table(
        "index_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_index_jobs_repo_id"), "index_jobs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_index_jobs_status"), "index_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_index_jobs_created_at"), "index_jobs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("index_jobs")
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_tsv;")
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_embedding_hnsw;")
    op.drop_table("code_chunks")
    op.drop_table("repo_files")
    op.drop_index(op.f("ix_repositories_index_status"), table_name="repositories")
    op.drop_column("repositories", "chunk_count")
    op.drop_column("repositories", "indexed_at")
    op.drop_column("repositories", "indexed_commit_sha")
    op.drop_column("repositories", "index_status")
