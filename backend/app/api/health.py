import logging
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core.security import hash_token, session_expiry
from app.models import (
    AccountSession,
    AnonymousSession,
    ChatRequest,
    Conversation,
    Message,
    MessageFeedback,
    MessageVersion,
    Project,
    RegenerationRequest,
    User,
)
from app.models.chat import LimitBucket
from app.services.limits import consume

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness does not contact dependencies, so it detects a working process."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request, response: Response) -> dict[str, str]:
    try:
        with request.app.state.session_factory() as db:
            # Validate migrated columns, not just connectivity or table existence.
            for model in (
                AnonymousSession,
                Conversation,
                Message,
                ChatRequest,
                LimitBucket,
                User,
                AccountSession,
                Project,
                MessageVersion,
                MessageFeedback,
                RegenerationRequest,
            ):
                db.execute(select(model).limit(0))
            # Exercise the first request's writes too: SELECT can succeed under RLS
            # even when INSERT is forbidden. These probes are always rolled back.
            consume(db, f"readiness:{uuid4()}", 1, 1, 60)
            db.add(
                AnonymousSession(token_hash=hash_token(str(uuid4())), expires_at=session_expiry())
            )
            db.flush()
            db.rollback()
        return {"status": "ready", "database": "ok"}
    except Exception:
        logger.exception(
            "database readiness failed",
            extra={
                "event": "database.readiness.failed",
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        response.status_code = 503
        return {"status": "not_ready", "database": "unavailable"}
