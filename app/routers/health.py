import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import engine

router = APIRouter()


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    client = aioredis.from_url(settings.redis_url)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get("/health")
async def health():
    db_ok, redis_ok = await check_db(), await check_redis()
    body = {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "db": "up" if db_ok else "down",
        "redis": "up" if redis_ok else "down",
    }
    return JSONResponse(body, status_code=200 if db_ok and redis_ok else 503)
