import asyncio
import logging
from typing import Optional
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import settings

logger = logging.getLogger(__name__)

_pool_lock = asyncio.Lock()
_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Obtain or initialize thread-safe pooled ARQ Redis connection."""
    global _arq_pool
    if _arq_pool is None:
        async with _pool_lock:
            if _arq_pool is None:
                _arq_pool = await create_pool(
                    RedisSettings.from_dsn(settings.redis_url),
                )
    return _arq_pool


async def close_arq_pool() -> None:
    """Gracefully close background ARQ connection pool."""
    global _arq_pool
    if _arq_pool is not None:
        async with _pool_lock:
            if _arq_pool is not None:
                try:
                    await _arq_pool.close()
                except Exception as exc:
                    logger.warning("Error closing ARQ pool: %s", exc)
                finally:
                    _arq_pool = None
