from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness does not contact dependencies, so it detects a working process."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Database readiness is added with the PostgreSQL implementation step."""
    return {"status": "ready", "database": "not_configured"}
