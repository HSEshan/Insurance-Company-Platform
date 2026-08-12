"""Shared async Redis client used for caching and login-attempt throttling."""

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis = Redis.from_url(
    str(settings.REDIS_URL),
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis() -> Redis:
    return redis_client
