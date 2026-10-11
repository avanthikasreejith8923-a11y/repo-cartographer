"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DEMO_MODE: bool = False
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Security
    SECRET_KEY: str = "development-secret-key-must-be-changed-in-production-min32"
    FERNET_KEY: str = "wT35dS02-oURvxyZ4MxSLsryyPEXsSux5WrDxZa2JaY="
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SESSION_COOKIE_NAME: str = "rc_session"
    OAUTH_STATE_COOKIE_NAME: str = "rc_oauth_state"

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "repo_cartographer"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/repo_cartographer"
    TEST_DATABASE_URL: str | None = None

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"
    ARQ_POLL_DELAY: float = 5.0  # seconds between queue polls to conserve hosted Redis commands

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/auth/github/callback"

    # Ingestion & Sync Job Limits
    SYNC_MAX_COMMITS: int = 500
    SYNC_MAX_PRS: int = 200
    SYNC_MAX_ISSUES: int = 500
    SYNC_STATS_COMMITS_LIMIT: int = 100
    SYNC_STATS_PRS_LIMIT: int = 50

    # Phase 3: Code Intelligence & Embeddings
    EMBEDDING_PROVIDER: str = "gemini"  # gemini | fake
    GEMINI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIM: int = 768
    EMBED_BATCH_SIZE: int = 32
    INDEX_MAX_FILES: int = 1500
    INDEX_MAX_FILE_BYTES: int = 200000
    INDEX_MAX_CHUNKS: int = 4000
    INDEX_MAX_REPO_DOWNLOAD_MB: int = 100

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Allow CORS_ORIGINS to be passed as JSON string or comma-separated list."""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i) for i in v]
        return v

    @staticmethod
    def normalize_asyncpg_dsn(url: str | None) -> str | None:
        """Normalize Neon and Postgres URLs for asyncpg driver."""
        if not url:
            return url
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        scheme = parsed.scheme
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+asyncpg"

        q = parse_qs(parsed.query)
        # asyncpg accepts ssl=require, but errors on libpq sslmode / channel_binding
        if "sslmode" in q:
            ssl_val = q.pop("sslmode")[0]
            if "ssl" not in q:
                q["ssl"] = [ssl_val]
        q.pop("channel_binding", None)

        flat_q = {k: v[0] for k, v in q.items()}
        new_query = urlencode(flat_q)
        return urlunparse(parsed._replace(scheme=scheme, query=new_query))

    @staticmethod
    def normalize_sync_dsn(url: str | None) -> str | None:
        """Normalize URL for synchronous drivers and Alembic migrations."""
        if not url:
            return url
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(url)
        scheme = "postgresql" if "postgres" in parsed.scheme else parsed.scheme

        q = parse_qs(parsed.query)
        if "ssl" in q:
            ssl_val = q.pop("ssl")[0]
            if "sslmode" not in q:
                q["sslmode"] = [ssl_val]
        q.pop("channel_binding", None)

        flat_q = {k: v[0] for k, v in q.items()}
        new_query = urlencode(flat_q)
        return urlunparse(parsed._replace(scheme=scheme, query=new_query))

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str) -> str:
        """Normalize DATABASE_URL for asyncpg."""
        normalized = cls.normalize_asyncpg_dsn(v)
        return normalized or v

    @field_validator("TEST_DATABASE_URL", mode="before")
    @classmethod
    def assemble_test_database_url(cls, v: str | None) -> str | None:
        """Normalize TEST_DATABASE_URL for asyncpg if provided."""
        if not v:
            return None
        return cls.normalize_asyncpg_dsn(v)

    @property
    def is_production(self) -> bool:
        """Helper to determine if running in production."""
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def is_db_pooler(self) -> bool:
        """Check if database host is a Neon transaction pooler (-pooler)."""
        from urllib.parse import urlparse

        parsed = urlparse(self.DATABASE_URL)
        return bool(parsed.hostname and "-pooler" in parsed.hostname.lower())

    @property
    def asyncpg_connect_args(self) -> dict[str, Any]:
        """Connection arguments for asyncpg. Disables statement caching on poolers."""
        from typing import Any

        connect_args: dict[str, Any] = {}
        if self.is_db_pooler:
            # Transaction poolers like pgbouncer on Neon do not support prepared statements
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0
        return connect_args

    @property
    def sync_database_url(self) -> str:
        """Return synchronous database URL for Alembic migrations."""
        return self.normalize_sync_dsn(self.DATABASE_URL) or self.DATABASE_URL

    def validate_test_database_url(self) -> str:
        """Validate TEST_DATABASE_URL for isolated testing.

        Strictly refuses to run if unset, equal to DATABASE_URL, or if database name
        does not contain 'test'. Prevents accidental destruction of main/production database.
        """
        if not self.TEST_DATABASE_URL or not self.TEST_DATABASE_URL.strip():
            raise ValueError(
                "TEST_DATABASE_URL is not configured. Integration tests refuse to run without an isolated test database."
            )

        from urllib.parse import urlparse

        parsed_test = urlparse(self.TEST_DATABASE_URL)

        if self.TEST_DATABASE_URL.strip() == self.DATABASE_URL.strip():
            raise ValueError(
                "TEST_DATABASE_URL cannot be identical to DATABASE_URL. Refusing to run tests on primary database."
            )

        test_db_name = (parsed_test.path or "").lstrip("/").lower()
        if "test" not in test_db_name:
            raise ValueError(
                f"TEST_DATABASE_URL database name '{test_db_name}' must contain 'test'. Refusing to run tests on non-test DB."
            )

        return self.TEST_DATABASE_URL



@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()


settings = get_settings()
