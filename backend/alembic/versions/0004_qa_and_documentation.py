"""Add qa_history and repo_docs tables for Phase 4 Q&A and Documentation.

Revision ID: 0004_qa_and_documentation
Revises: 0003_code_intelligence
Create Date: 2026-10-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_qa_and_documentation"
down_revision: str | None = "0003_code_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. qa_history table
    op.create_table(
        "qa_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="ok", nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_qa_history_repo_id"), "qa_history", ["repo_id"], unique=False)
    op.create_index(op.f("ix_qa_history_user_id"), "qa_history", ["user_id"], unique=False)
    op.create_index("ix_qa_history_repo_user_created", "qa_history", ["repo_id", "user_id", "created_at"], unique=False)

    # 2. repo_docs table
    op.create_table(
        "repo_docs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "doc_type", name="uq_repo_docs_repo_doc_type"),
    )
    op.create_index(op.f("ix_repo_docs_repo_id"), "repo_docs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_repo_docs_status"), "repo_docs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("repo_docs")
    op.drop_table("qa_history")
