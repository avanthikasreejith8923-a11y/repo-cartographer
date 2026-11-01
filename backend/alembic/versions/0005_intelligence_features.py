"""Add pr_analyses, issue_analyses, generated_tests, and analysis_jobs tables.

Revision ID: 0005_intelligence_features
Revises: 0004_qa_and_documentation
Create Date: 2026-10-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "0005_intelligence_features"
down_revision: str | None = "0004_qa_and_documentation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. pr_analyses table
    op.create_table(
        "pr_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("summary_markdown", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), server_default="low", nullable=False),
        sa.Column("risk_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("risk_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("files_analyzed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ok", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "pr_number", name="uq_pr_analyses_repo_pr"),
    )
    op.create_index(op.f("ix_pr_analyses_repo_id"), "pr_analyses", ["repo_id"], unique=False)
    op.create_index(op.f("ix_pr_analyses_risk_level"), "pr_analyses", ["risk_level"], unique=False)

    # 2. issue_analyses table
    op.create_table(
        "issue_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(settings.EMBEDDING_DIM), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "issue_number", name="uq_issue_analyses_repo_issue"),
    )
    op.create_index(op.f("ix_issue_analyses_repo_id"), "issue_analyses", ["repo_id"], unique=False)
    op.create_index(op.f("ix_issue_analyses_issue_type"), "issue_analyses", ["issue_type"], unique=False)

    # 3. generated_tests table
    op.create_table(
        "generated_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("framework", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("syntax_valid", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_generated_tests_repo_path_created", "generated_tests", ["repo_id", "path", "created_at"], unique=False)
    op.create_index(op.f("ix_generated_tests_repo_id"), "generated_tests", ["repo_id"], unique=False)
    op.create_index(op.f("ix_generated_tests_user_id"), "generated_tests", ["user_id"], unique=False)

    # 4. analysis_jobs table
    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_analysis_jobs_repo_id"), "analysis_jobs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("analysis_jobs")
    op.drop_table("generated_tests")
    op.drop_table("issue_analyses")
    op.drop_table("pr_analyses")
