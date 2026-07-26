"""
FKG REST API — Main FastAPI application entry point.

Routing structure:
  /                    — Single Holistic Dashboard SPA
  /dashboard           — Single Holistic Dashboard SPA
  /health              — Health liveness check
  /health/ready        — Health readiness check
  /metrics             — Prometheus scrape endpoint
  /v1/dishes/*         — Dish search, detail, similar, variants
  /v1/dashboard/*      — Telemetry, services, graph, trigger endpoints
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from prometheus_fastapi_instrumentator import Instrumentator

from fkg_api.routers import dashboard, dishes, health

log = structlog.get_logger()
TEMPLATES_DIR = Path(__file__).parent / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    log.info("fkg_api.startup")
    yield
    log.info("fkg_api.shutdown")


def create_app() -> FastAPI:
    """Application factory — returns configured FastAPI instance."""
    app = FastAPI(
        title="Food Knowledge Graph API",
        description=(
            "REST API for the world's largest Food Knowledge Graph. "
            "Covers 250+ countries, 10,000+ cuisines, and 250,000+ dishes."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus instrumentation ────────────────────────────────────────────
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # ── Holistic Dashboard Single Page Application ─────────────────────────────
    @app.get("/", response_class=HTMLResponse, summary="Holistic Dashboard SPA")
    @app.get("/dashboard", response_class=HTMLResponse, summary="Holistic Dashboard SPA")
    async def dashboard_spa():
        html_path = TEMPLATES_DIR / "dashboard.html"
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = "/v1"
    app.include_router(health.router, tags=["Health"])
    app.include_router(dishes.router, prefix=f"{prefix}/dishes", tags=["Dishes"])
    app.include_router(dashboard.router, prefix=f"{prefix}/dashboard", tags=["Dashboard"])

    return app


app = create_app()
