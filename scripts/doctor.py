"""Doctor script: validates configuration, infrastructure connectivity, and AI providers.

Usage:
    python scripts/doctor.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings
from app.services.embeddings import get_embedding_provider


class DoctorReport:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def record(self, check_name: str, passed: bool, message: str) -> None:
        self.results.append((check_name, passed, message))

    def print_summary(self) -> bool:
        print("\n" + "=" * 70)
        print("          REPO-CARTOGRAPHER ENVIRONMENT & SERVICE DOCTOR")
        print("=" * 70)
        all_passed = True
        for name, passed, details in self.results:
            status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
            # Plain fallback if terminal does not support ANSI
            if not sys.stdout.isatty():
                status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"[{status:^4}] {name:<28} : {details}")
        print("=" * 70)
        if all_passed:
            print("\033[92mAll system checks passed successfully!\033[0m\n")
        else:
            print("\033[91mOne or more system checks failed. Review details above.\033[0m\n")
        return all_passed


async def check_env_vars(report: DoctorReport) -> None:
    required_vars = [
        ("DATABASE_URL", bool(settings.DATABASE_URL)),
        ("REDIS_URL", bool(settings.REDIS_URL)),
        ("SECRET_KEY", bool(settings.SECRET_KEY)),
        ("FERNET_KEY", bool(settings.FERNET_KEY)),
    ]
    missing = [name for name, present in required_vars if not present]
    if missing:
        report.record("Environment Variables", False, f"Missing required variables: {', '.join(missing)}")
    else:
        report.record("Environment Variables", True, "Core configuration variables present")


async def check_database_and_vector(report: DoctorReport) -> None:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        connect_args=settings.asyncpg_connect_args,
    )
    try:
        async with engine.connect() as conn:
            # 1. DB Reachable
            res = await conn.execute(sa.text("SELECT 1"))
            if res.scalar() == 1:
                report.record("Database Reachable", True, "Successfully connected to PostgreSQL")
            else:
                report.record("Database Reachable", False, "Query executed but returned unexpected result")

            # 2. Vector Extension
            ext_res = await conn.execute(
                sa.text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            )
            count = ext_res.scalar() or 0
            if count > 0:
                report.record("pgvector Extension", True, "Extension 'vector' is installed and active")
            else:
                report.record("pgvector Extension", False, "Extension 'vector' is not installed in database")

            # 3. Alembic Head Revision
            try:
                ver_res = await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
                versions = [r[0] for r in ver_res.fetchall()]
                expected_head = "0003_code_intelligence"
                if expected_head in versions:
                    report.record("Alembic Migrations", True, f"Schema at head revision ({expected_head})")
                else:
                    report.record(
                        "Alembic Migrations",
                        False,
                        f"Current version {versions} does not match head ({expected_head}). Run scripts/dev-migrate.ps1",
                    )
            except Exception as e:  # noqa: BLE001
                report.record(
                    "Alembic Migrations",
                    False,
                    f"alembic_version table not found or unreadable. Run scripts/dev-migrate.ps1 ({type(e).__name__})",
                )

    except Exception as exc:  # noqa: BLE001
        report.record("Database Reachable", False, f"Connection failed: {type(exc).__name__}")
        report.record("pgvector Extension", False, "Skipped due to DB connection failure")
        report.record("Alembic Migrations", False, "Skipped due to DB connection failure")
    finally:
        await engine.dispose()


async def check_redis(report: DoctorReport) -> None:
    from redis.asyncio import Redis

    try:
        client = Redis.from_url(settings.REDIS_URL)
        pong = await client.ping()
        if pong:
            report.record("Redis Reachable", True, "Successfully pinged Redis instance")
        else:
            report.record("Redis Reachable", False, "Ping returned False")
        await client.aclose()
    except Exception as exc:  # noqa: BLE001
        report.record("Redis Reachable", False, f"Connection failed: {type(exc).__name__}")


async def check_github_oauth(report: DoctorReport) -> None:
    has_id = bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_ID.strip())
    has_secret = bool(settings.GITHUB_CLIENT_SECRET and settings.GITHUB_CLIENT_SECRET.strip())
    if has_id and has_secret:
        report.record("GitHub OAuth Config", True, "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are configured")
    else:
        missing = []
        if not has_id:
            missing.append("GITHUB_CLIENT_ID")
        if not has_secret:
            missing.append("GITHUB_CLIENT_SECRET")
        report.record("GitHub OAuth Config", False, f"Missing: {', '.join(missing)}")


async def check_embeddings(report: DoctorReport) -> None:
    try:
        provider = get_embedding_provider()
        sample_text = "Repo Cartographer Doctor Probe"
        vector = await provider.embed_query(sample_text)
        expected_dim = settings.EMBEDDING_DIM
        if len(vector) == expected_dim:
            provider_name = type(provider).__name__
            report.record(
                "Embedding Provider",
                True,
                f"{provider_name} successfully generated {len(vector)}-dim vector",
            )
        else:
            report.record(
                "Embedding Provider",
                False,
                f"Dimension mismatch: expected {expected_dim}, got {len(vector)}",
            )
    except Exception as exc:  # noqa: BLE001
        report.record("Embedding Provider", False, f"Embedding generation failed: {type(exc).__name__}: {exc}")


async def check_test_database(report: DoctorReport) -> None:
    if not settings.TEST_DATABASE_URL:
        report.record("Test Database", False, "TEST_DATABASE_URL is not set in .env (needed for isolated tests)")
        return
    try:
        settings.validate_test_database_url()
    except Exception as exc:  # noqa: BLE001
        report.record("Test Database", False, f"Invalid TEST_DATABASE_URL: {exc}")
        return

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        echo=False,
        connect_args=settings.asyncpg_connect_args,
    )
    try:
        async with engine.connect() as conn:
            res = await conn.execute(sa.text("SELECT 1"))
            if res.scalar() != 1:
                report.record("Test Database", False, "Query executed but returned unexpected result")
                return

            ext_res = await conn.execute(
                sa.text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            )
            count = ext_res.scalar() or 0
            if count > 0:
                report.record("Test Database", True, "Reachable; pgvector extension active")
            else:
                report.record("Test Database", False, "Reachable, but 'vector' extension is not installed")
    except Exception as exc:  # noqa: BLE001
        report.record("Test Database", False, f"Connection failed: {type(exc).__name__}")
    finally:
        await engine.dispose()


async def run_doctor() -> bool:
    report = DoctorReport()
    await check_env_vars(report)
    await check_database_and_vector(report)
    await check_test_database(report)
    await check_redis(report)
    await check_github_oauth(report)
    await check_embeddings(report)
    return report.print_summary()



if __name__ == "__main__":
    success = asyncio.run(run_doctor())
    sys.exit(0 if success else 1)
