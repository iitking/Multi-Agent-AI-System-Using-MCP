"""FastAPI entry point for the Enterprise Multi-Agent AI System."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.config import get_settings
from backend.database.models import init_app_db
from backend.database.seed import ensure_seeded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("Initializing application in '%s' environment...", settings.app_env)

    # Initialize app database tables
    try:
        init_app_db()
        logger.info("App database initialized.")
    except Exception as exc:
        logger.error("Failed to initialize app database: %s", exc)
        raise

    # Seed analytics dataset if needed
    try:
        row_count = ensure_seeded()
        logger.info("Analytics sales database ready (%d rows).", row_count)
    except Exception as exc:
        logger.error("Failed to seed analytics database: %s", exc)
        raise

    yield
    logger.info("Application shutting down...")


app = FastAPI(
    title="Enterprise Multi-Agent AI System Using MCP",
    description=(
        "Production-ready multi-agent analytics platform orchestrating LangGraph, "
        "Model Context Protocol (MCP), LangSmith, and n8n."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add secure HTTP headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# Include API routes
app.include_router(api_router)


@app.get("/", tags=["Health"])
def root_status() -> dict[str, str]:
    return {
        "service": "Enterprise Multi-Agent AI System",
        "status": "online",
        "docs": "/docs",
        "api": "/api",
    }


@app.get("/health", tags=["Health"])
def health_endpoint() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard", tags=["Dashboard"])
def dashboard_endpoint():
    from pathlib import Path
    from fastapi.responses import FileResponse

    html_file = Path(__file__).parent / "static" / "dashboard.html"
    return FileResponse(html_file, media_type="text/html")


if __name__ == "__main__":
    from pathlib import Path
    import uvicorn

    backend_dir = str(Path(__file__).parent)
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[backend_dir],
    )
