"""FastAPI Application entrypoint for repo-cartographer."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.session import verify_db_connection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and graceful shutdown."""
    setup_logging()
    if settings.DEMO_MODE:
        logger.warning("=" * 70)
        logger.warning("!!! WARNING: DEMO MODE IS ENABLED !!!")
        logger.warning("Live database and Redis are bypassed with in-memory stores.")
        logger.warning("=" * 70)
    else:
        logger.info(f"Starting repo-cartographer backend [Environment: {settings.ENVIRONMENT}]")
        logger.info(f"Database target: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
        logger.info(f"Redis target: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        await verify_db_connection()
    yield
    logger.info("Shutting down repo-cartographer backend services...")


def create_application() -> FastAPI:
    """Create and configure FastAPI instance."""
    app = FastAPI(
        title="repo-cartographer API",
        description="AI Developer Productivity Platform: Codebase Graphing, Ingestion, and RAG",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # Configure CORS for frontend access with credentials (cookies)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(api_router)

    @app.get("/", summary="Root Health & Metadata")
    async def root_status() -> JSONResponse:
        return JSONResponse({
            "service": "repo-cartographer-api",
            "version": "0.1.0",
            "phase": "Phase 1: Foundation + GitHub OAuth",
            "docs": "/docs" if settings.DEBUG else "disabled",
            "status": "online",
        })

    return app


app = create_application()
