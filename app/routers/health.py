import logging
import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import engine

logger = logging.getLogger(__name__)
router = APIRouter()


async def check_db() -> bool:
    """Ping database connection pool."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.debug("Database healthcheck ping failed: %s", exc)
        return False


async def check_redis() -> bool:
    """Ping Redis server."""
    client = aioredis.from_url(settings.redis_url, socket_timeout=2.0)
    try:
        return bool(await client.ping())
    except Exception as exc:
        logger.debug("Redis healthcheck ping failed: %s", exc)
        return False
    finally:
        await client.aclose()


@router.get(
    "/health",
    summary="Service health and readiness check",
    response_description="Operational status of API, database, and Redis cache",
)
async def health():
    db_ok, redis_ok = await check_db(), await check_redis()
    all_healthy = db_ok and redis_ok

    payload = {
        "status": "ok" if all_healthy else "degraded",
        "db": "up" if db_ok else "down",
        "redis": "up" if redis_ok else "down",
    }
    return JSONResponse(
        content=payload,
        status_code=200 if all_healthy else 503,
    )
