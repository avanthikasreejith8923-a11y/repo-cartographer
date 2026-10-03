"""Add repositories, commits, pull requests, issues, and sync jobs tables.

Revision ID: 0002_ingestion_tables
Revises: 0001_initial_schema
Create Date: 2026-10-03 07:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_ingestion_tables"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Repositories table
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=100), nullable=False, server_default="main"),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "github_id", name="uq_repositories_user_github"),
    )
    op.create_index(op.f("ix_repositories_user_id"), "repositories", ["user_id"], unique=False)
    op.create_index(op.f("ix_repositories_github_id"), "repositories", ["github_id"], unique=False)
    op.create_index(op.f("ix_repositories_full_name"), "repositories", ["full_name"], unique=False)
    op.create_index(op.f("ix_repositories_status"), "repositories", ["status"], unique=False)

    # 2. Commits table
    op.create_table(
        "commits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha", sa.String(length=40), nullable=False),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("files_changed", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "sha", name="uq_commits_repo_sha"),
    )
    op.create_index(op.f("ix_commits_repo_id"), "commits", ["repo_id"], unique=False)
    op.create_index(op.f("ix_commits_committed_at"), "commits", ["committed_at"], unique=False)
    op.create_index(op.f("ix_commits_author_login"), "commits", ["author_login"], unique=False)

    # 3. Pull Requests table
    op.create_table(
        "pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("additions", sa.Integer(), nullable=True),
        sa.Column("deletions", sa.Integer(), nullable=True),
        sa.Column("changed_files", sa.Integer(), nullable=True),
        sa.Column("base_ref", sa.String(length=255), nullable=True),
        sa.Column("head_ref", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "number", name="uq_pull_requests_repo_number"),
    )
    op.create_index(op.f("ix_pull_requests_repo_id"), "pull_requests", ["repo_id"], unique=False)
    op.create_index(op.f("ix_pull_requests_created_at"), "pull_requests", ["created_at"], unique=False)
    op.create_index(op.f("ix_pull_requests_state"), "pull_requests", ["state"], unique=False)
    op.create_index(op.f("ix_pull_requests_author_login"), "pull_requests", ["author_login"], unique=False)

    # 4. Issues table
    op.create_table(
        "issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("repo_id", "number", name="uq_issues_repo_number"),
    )
    op.create_index(op.f("ix_issues_repo_id"), "issues", ["repo_id"], unique=False)
    op.create_index(op.f("ix_issues_created_at"), "issues", ["created_at"], unique=False)
    op.create_index(op.f("ix_issues_state"), "issues", ["state"], unique=False)
    op.create_index(op.f("ix_issues_author_login"), "issues", ["author_login"], unique=False)

    # 5. Sync Jobs table
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_sync_jobs_repo_id"), "sync_jobs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_sync_jobs_status"), "sync_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_sync_jobs_created_at"), "sync_jobs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("sync_jobs")
    op.drop_table("issues")
    op.drop_table("pull_requests")
    op.drop_table("commits")
    op.drop_table("repositories")
