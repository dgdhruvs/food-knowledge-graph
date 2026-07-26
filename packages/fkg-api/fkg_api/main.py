"""
FKG REST API — Main FastAPI application entry point.

Routing structure:
  /v1/dishes/*         — Dish search, detail, similar, variants
  /v1/cuisines/*       — Cuisine search, hierarchy
  /v1/ingredients/*    — Ingredient search, substitutions
  /v1/countries/*      — Country and cuisine listing
  /v1/search           — Unified cross-entity search
  /v1/autocomplete     — Prefix autocomplete
  /v1/recommend/*      — Recommendation endpoints
  /v1/graph/*          — Graph traversal endpoints
  /health              — Health check
  /metrics             — Prometheus scrape endpoint

Design decisions:
- All endpoints are async (asyncpg + Neo4j async driver)
- Redis caching layer: TTL varies by entity stability
  (countries: 24h, cuisines: 6h, dishes: 1h, search: 5min)
- Rate limiting: 100 req/min (free), 10,000/min (enterprise)
- OpenAPI docs auto-generated at /docs
- Prometheus metrics auto-instrumented
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from fkg_api.routers import (
    autocomplete,
    countries,
    cuisines,
    dishes,
    graph,
    health,
    ingredients,
    recommendations,
    search,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    log.info("fkg_api.startup")
    # TODO: Initialize DB connection pools, Redis client, Neo4j driver
    yield
    log.info("fkg_api.shutdown")
    # TODO: Gracefully close all connections


def create_app() -> FastAPI:
    """Application factory — returns the configured FastAPI instance."""
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
        allow_origins=["*"],  # Tighten in production to specific domains
        allow_credentials=True,
        allow_methods=["GET"],  # Read-only public API
        allow_headers=["*"],
    )

    # ── Prometheus instrumentation ────────────────────────────────────────────
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # ── Routers ───────────────────────────────────────────────────────────────
    prefix = "/v1"
    app.include_router(health.router, tags=["Health"])
    app.include_router(dishes.router, prefix=f"{prefix}/dishes", tags=["Dishes"])
    app.include_router(cuisines.router, prefix=f"{prefix}/cuisines", tags=["Cuisines"])
    app.include_router(ingredients.router, prefix=f"{prefix}/ingredients", tags=["Ingredients"])
    app.include_router(countries.router, prefix=f"{prefix}/countries", tags=["Countries"])
    app.include_router(search.router, prefix=f"{prefix}/search", tags=["Search"])
    app.include_router(autocomplete.router, prefix=f"{prefix}/autocomplete", tags=["Autocomplete"])
    app.include_router(recommendations.router, prefix=f"{prefix}/recommend", tags=["Recommendations"])
    app.include_router(graph.router, prefix=f"{prefix}/graph", tags=["Graph Traversal"])

    return app


app = create_app()
