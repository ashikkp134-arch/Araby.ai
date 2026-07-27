"""Redis connection and cache helpers."""

import logging
from typing import Optional

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: Optional[redis.Redis] = None


async def connect_to_redis() -> None:
    """Establish a connection to Redis.

    Raises:
        Exception: Propagated connection failures after logging.
    """
    global _redis
    settings = get_settings()
    _redis = redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()
    logger.info("Connected to Redis")


async def close_redis_connection() -> None:
    """Close the active Redis connection."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis:
    """Return the active Redis client.

    Returns:
        Async Redis client instance.

    Raises:
        RuntimeError: If Redis has not been initialized.
    """
    if _redis is None:
        raise RuntimeError("Redis is not initialized")
    return _redis


class RedisCache:
    """Thin helper around Redis for typed cache operations."""

    def __init__(self, client: redis.Redis) -> None:
        """Initialize the cache helper.

        Args:
            client: Async Redis client.
        """
        self._client = client

    async def get(self, key: str) -> Optional[str]:
        """Get a string value by key.

        Args:
            key: Cache key.

        Returns:
            Cached string or None.
        """
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Set a string value with TTL.

        Args:
            key: Cache key.
            value: Value to store.
            ttl_seconds: Time-to-live in seconds.
        """
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        """Delete a cache key.

        Args:
            key: Cache key to remove.
        """
        await self._client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check whether a key exists.

        Args:
            key: Cache key.

        Returns:
            True if the key exists.
        """
        return bool(await self._client.exists(key))

    async def incr(self, key: str) -> int:
        """Increment a counter key.

        Args:
            key: Counter key.

        Returns:
            New counter value.
        """
        return int(await self._client.incr(key))

    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Set expiry on an existing key.

        Args:
            key: Cache key.
            ttl_seconds: Time-to-live in seconds.
        """
        await self._client.expire(key, ttl_seconds)
