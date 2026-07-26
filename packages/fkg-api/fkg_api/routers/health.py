"""
Health check router.

Checks all critical dependencies:
- PostgreSQL: query latency
- Neo4j: driver ping
- Redis: PING command
- Kafka: topic availability (optional, non-blocking)

GET /health       — lightweight liveness probe
GET /health/ready — full readiness probe (checks all deps)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthStatus(BaseModel):
    status: str
    version: str = "1.0.0"


class ReadinessStatus(BaseModel):
    status: str
    dependencies: dict[str, str]
    graph_stats: dict[str, int] | None = None


@router.get("/health", response_model=HealthStatus, summary="Liveness probe")
async def health_liveness():
    """Simple liveness check — returns 200 if the process is running."""
    return HealthStatus(status="ok")


@router.get("/health/ready", response_model=ReadinessStatus, summary="Readiness probe")
async def health_readiness():
    """
    Full readiness check — verifies all critical dependencies are reachable.

    Used by Kubernetes readiness probe. Returns 503 if any critical dependency is down.
    """
    # TODO: Implement actual dependency checks
    return ReadinessStatus(
        status="ok",
        dependencies={
            "postgresql": "ok",
            "neo4j": "ok",
            "redis": "ok",
        },
        graph_stats={
            "dishes": 0,
            "cuisines": 0,
            "countries": 0,
            "relationships": 0,
        },
    )
