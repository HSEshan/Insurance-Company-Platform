"""Health and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas.common import ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return ok({"status": "ok"})


@router.get("/ready")
async def ready(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    checks = {"db": "ok", "redis": "ok", "storage": "ok"}
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "error"
    try:
        await redis.ping()
    except Exception:
        checks["redis"] = "error"
    if not await storage.check_connection():
        checks["storage"] = "error"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ok({"status": status, **checks})
