"""Health endpoints for liveness/readiness checks."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/live", summary="Liveness probe")
async def liveness_probe() -> dict:
    """Returns a trivial response so container orchestrators know the app is up."""
    return {"status": "alive"}
    

@router.get("/ready", summary="Readiness probe")
async def readiness_probe() -> dict:
    return {"status": "ok", "mongo": "pending", "openai": "pending"}
"""Placeholder readiness endpoint; will later validate Mongo/OpenAI readiness."""
	