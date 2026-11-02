from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness does not contact dependencies, so it detects a working process."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    try:
        with request.app.state.session_factory() as db:
            db.execute(text("SELECT 1 FROM limit_buckets LIMIT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "database": "unavailable"}
