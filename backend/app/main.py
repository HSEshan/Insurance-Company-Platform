"""FastAPI application factory and global wiring."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core import request_context, storage
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.redis_client import redis_client

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.APP_ENV)
    try:
        await storage.ensure_buckets()
    except Exception:
        # Object storage is only needed for document endpoints, so a MinIO
        # outage should degrade uploads rather than block the whole API.
        logger.warning("Could not reach MinIO; document uploads unavailable.")
    yield
    await redis_client.aclose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_request_id(raw: str | None) -> uuid.UUID:
    if raw:
        try:
            return uuid.UUID(raw)
        except (ValueError, AttributeError, TypeError):
            pass
    return uuid.uuid4()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Stamp every request with a correlating id + forensic metadata for audit."""
    request_id = _parse_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = str(request_id)
    request_context.set_request_context(
        request_id=request_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request_id)
        return response
    finally:
        request_context.clear_request_context()


def _error_response(
    status_code: int, code: str, message: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "meta": None,
            "error": {"code": code, "message": message, "details": details or {}},
        },
    )


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"errors": jsonable_encoder(exc.errors())},
    )


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root() -> dict:
    return {"name": settings.APP_NAME, "docs": "/api/docs"}
