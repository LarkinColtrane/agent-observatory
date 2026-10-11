"""observatory.cache (ADR-0005): Redis client and Redis health check."""

from observatory.cache.client import create_redis, redis_check

__all__ = ["create_redis", "redis_check"]
