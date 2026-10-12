"""Redis client and readiness check (ADR-0005 §3).

The URL is read with ``get_secret_value()`` only here, at the point of use,
and never logged or placed in exception messages. Nothing is created at
import time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import ConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from observatory.core.config import ConfigurationError
from observatory.core.health import HealthCheck, make_check

if TYPE_CHECKING:
    from observatory.core.config import Settings  # noqa: TID251 (type only)

SOCKET_TIMEOUT_S = 1
SOCKET_CONNECT_TIMEOUT_S = 1
# Hard cap on connections per client. The pool is a plain (non-blocking)
# ConnectionPool: once the cap is reached a further command fails at once with
# MaxConnectionsError instead of opening another socket or waiting, so a burst
# of readiness probes (an unauthenticated endpoint) cannot exhaust Redis.
MAX_CONNECTIONS = 16


def create_redis(settings: Settings) -> Redis:
    """Create the application's Redis client from ``settings.redis_url``.

    Does not connect; connections are opened lazily. At most
    ``MAX_CONNECTIONS`` connections exist at once; excess commands fail
    immediately. Retries are disabled so a command fails within the socket
    timeouts (redis-py's default retries would stretch an outage well past
    readiness deadlines). The client owns its pool; the caller must
    ``await client.aclose()`` on shutdown, which also closes the pool.
    """
    if settings.redis_url is None:
        raise ConfigurationError("AO_REDIS_URL is not set")
    pool: ConnectionPool | None = None
    try:
        pool = ConnectionPool.from_url(
            settings.redis_url.get_secret_value(),
            max_connections=MAX_CONNECTIONS,
            socket_timeout=SOCKET_TIMEOUT_S,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT_S,
            retry=Retry(NoBackoff(), retries=0),
        )
    except Exception:  # parse errors may embed the raw URL: never chain them
        pool = None
    if pool is None:
        # Raised outside the except block: no __context__ reference to the original error.
        raise ConfigurationError("AO_REDIS_URL is not a valid Redis URL (redis://, rediss://, unix://)")
    return Redis.from_pool(pool)


def redis_check(client: Redis) -> HealthCheck:
    """Readiness check named ``redis``: ``PING``.

    Time-boxing and fail-closed semantics come from ``core.health.run_checks``.
    """

    async def probe() -> None:
        if not await client.ping():
            raise RuntimeError("PING returned a falsy reply")

    return make_check("redis", probe)
