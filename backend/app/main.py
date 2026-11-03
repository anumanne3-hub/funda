import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_token
from app.db.session import SessionLocal
from app.providers import get_provider
from app.services.limits import RequestRejected, consume

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("application started", extra={"event": "application.started"})
    yield
    logger.info("application stopped", extra={"event": "application.stopped"})


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.state.session_factory = SessionLocal
app.state.llm_provider = get_provider(settings)
app.include_router(health_router)
app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(conversations_router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    origin = request.headers.get("origin")
    if request.method == "POST" and (
        (origin and origin not in settings.frontend_origins)
        or (settings.app_env == "production" and not origin)
    ):
        return JSONResponse(
            status_code=403,
            content={
                "code": "ORIGIN_REJECTED",
                "message": "Origin is not allowed",
                "request_id": request_id,
            },
        )
    try:
        if request.method == "POST":
            with request.app.state.session_factory() as db:
                ip = request.client.host if request.client else "unknown"
                consume(db, f"http:{hash_token(ip)}", 1, settings.sessions_per_minute, 60)
                db.commit()
        response = await call_next(request)
    except RequestRejected as exc:
        response = JSONResponse(
            status_code=429,
            content={
                "code": exc.code,
                "message": "Request limit reached",
                "request_id": request_id,
            },
            headers={"Retry-After": "60"},
        )
    except Exception:
        logger.exception(
            "request failed", extra={"event": "http.request.failed", "request_id": request_id}
        )
        response = JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "The request could not be completed",
                "request_id": request_id,
            },
        )
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request completed",
        extra={
            "event": "http.request.completed",
            "request_id": request_id,
        },
    )
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - started) * 1000:.1f}"
    return response


# Register last so CORS also covers responses created by request_context.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"],
)

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_REQUEST",
            "message": "Request validation failed",
            "request_id": getattr(request.state, "request_id", None),
        },
    )
