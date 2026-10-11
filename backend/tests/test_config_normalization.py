"""Unit tests for database URL normalization, pooler configuration, and test isolation."""

from unittest.mock import patch

import pytest

from app.core.config import Settings


def test_normalize_asyncpg_dsn_neon_url() -> None:
    """Ensure standard Neon URL with sslmode and channel_binding normalizes for asyncpg."""
    neon_url = "postgresql://user:pass@ep-cool-12345.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    normalized = Settings.normalize_asyncpg_dsn(neon_url)

    assert normalized is not None
    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode" not in normalized
    assert "channel_binding" not in normalized


def test_normalize_asyncpg_dsn_already_asyncpg() -> None:
    """Ensure already-prefixed URL preserves scheme while normalizing query params."""
    url = "postgresql+asyncpg://user:pass@localhost:5432/testdb?sslmode=require"
    normalized = Settings.normalize_asyncpg_dsn(url)

    assert normalized is not None
    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode" not in normalized


def test_normalize_sync_dsn_for_alembic() -> None:
    """Ensure sync URL normalizes with standard postgresql scheme and sslmode."""
    async_url = "postgresql+asyncpg://user:pass@ep-cool.aws.neon.tech/neondb?ssl=require&channel_binding=require"
    sync_url = Settings.normalize_sync_dsn(async_url)

    assert sync_url is not None
    assert sync_url.startswith("postgresql://")
    assert "sslmode=require" in sync_url
    assert "channel_binding" not in sync_url


def test_pooler_host_detection_and_connect_args() -> None:
    """Ensure -pooler hostname disables asyncpg prepared statement caching."""
    pooler_url = "postgresql://user:pass@ep-cool-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    with patch.dict("os.environ", {"DATABASE_URL": pooler_url}):
        s = Settings()
        assert s.is_db_pooler is True
        assert s.asyncpg_connect_args.get("statement_cache_size") == 0
        assert s.asyncpg_connect_args.get("prepared_statement_cache_size") == 0

    non_pooler_url = "postgresql://user:pass@ep-cool-direct.us-east-2.aws.neon.tech/neondb?sslmode=require"
    with patch.dict("os.environ", {"DATABASE_URL": non_pooler_url}):
        s2 = Settings()
        assert s2.is_db_pooler is False
        assert s2.asyncpg_connect_args == {}


def test_test_database_isolation_guard() -> None:
    """Ensure that integration tests refuse to run if TEST_DATABASE_URL is unset, equal to DATABASE_URL, or non-test."""
    main_url = "postgresql://user:pass@ep-cool.aws.neon.tech/neondb?sslmode=require"

    # 1. Unset -> ValueError
    with patch.dict("os.environ", {"DATABASE_URL": main_url, "TEST_DATABASE_URL": ""}):
        s_unset = Settings()
        with pytest.raises(ValueError, match="not configured"):
            s_unset.validate_test_database_url()

    # 2. Equal to main URL -> ValueError
    with patch.dict("os.environ", {"DATABASE_URL": main_url, "TEST_DATABASE_URL": main_url}):
        s_equal = Settings()
        with pytest.raises(ValueError, match="cannot be identical"):
            s_equal.validate_test_database_url()

    # 3. Database name does not contain 'test' -> ValueError
    prod_other_db = "postgresql://user:pass@ep-cool.aws.neon.tech/other_prod_db?sslmode=require"
    with patch.dict("os.environ", {"DATABASE_URL": main_url, "TEST_DATABASE_URL": prod_other_db}):
        s_notest = Settings()
        with pytest.raises(ValueError, match="must contain 'test'"):
            s_notest.validate_test_database_url()

    # 4. Valid isolated test database with 'test' in name -> succeeds
    valid_test_url = "postgresql://user:pass@ep-cool.aws.neon.tech/repo_test?sslmode=require"
    with patch.dict("os.environ", {"DATABASE_URL": main_url, "TEST_DATABASE_URL": valid_test_url}):
        s_valid = Settings()
        validated = s_valid.validate_test_database_url()
        assert "repo_test" in validated
        assert validated.startswith("postgresql+asyncpg://")

