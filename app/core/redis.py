from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        # Azure Cache for Redis uses TLS (rediss://) on port 6380.
        # Local dev uses plain redis:// on port 6379.
        # The scheme in REDIS_URL drives SSL automatically — no extra flag needed
        # EXCEPT we must set ssl_cert_reqs="none" for Azure's self-signed cert.
        is_tls = settings.REDIS_URL.startswith("rediss://")
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            ssl_cert_reqs="none" if is_tls else None,
        )
    return _redis
