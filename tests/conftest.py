import asyncio
import os
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Disable SQLAlchemy C-extensions on Windows environments with app restrictions
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"

import app.db
from app.db import Base, SessionLocal, engine, get_session
from app.main import app as fastapi_app
import app.models  # ensure models are registered with Base.metadata
import app.routers.jobs
import app.worker.tasks


async def _check_live_postgres() -> bool:
    """Check if the default configured PostgreSQL database is accessible."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Session fixture ensuring tests run either against live Postgres or an in-memory SQLite engine.

    Automatically provisions tables for hermetic testing if Postgres is not reachable.
    """
    loop = asyncio.new_event_loop()
    has_postgres = loop.run_until_complete(_check_live_postgres())

    if not has_postgres:
        test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        async def _init_sqlite():
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        loop.run_until_complete(_init_sqlite())

        # In-place reconfigure SessionLocal so all existing module imports immediately use test_engine
        SessionLocal.configure(bind=test_engine)
        app.db.engine = test_engine

        # Mock ARQ queue for fast, deterministic unit test runs without live Redis
        mock_arq = AsyncMock()
        mock_arq.enqueue_job = AsyncMock(return_value="mock_job_id")
        app.routers.jobs.get_arq_pool = AsyncMock(return_value=mock_arq)

        async def _override_get_session():
            async with SessionLocal() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        fastapi_app.dependency_overrides[get_session] = _override_get_session

    yield

    if not has_postgres:
        loop.run_until_complete(app.db.engine.dispose())
    else:
        loop.run_until_complete(engine.dispose())
    loop.close()
