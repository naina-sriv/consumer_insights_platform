import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Union

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# Engine configuration with connection pooling and pre-ping
_engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if "sqlite" not in settings.database_url:
    _engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_recycle": 1800,
        }
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)
SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy domain models."""
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for scoped transactional database sessions."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def scoped(query: Select[Any], tenant_id: Union[str, uuid.UUID]) -> Select[Any]:
    """
    Enforce strict tenant data isolation on SQLAlchemy select queries.

    Safely coerces string or UUID tenant identifiers and binds a tenant_id filter.
    """
    if isinstance(tenant_id, str):
        try:
            tenant_id = uuid.UUID(tenant_id)
        except ValueError:
            logger.warning("Invalid UUID passed to scoped query filter: %s", tenant_id)

    return query.filter_by(tenant_id=tenant_id)


async def dispose_engine() -> None:
    """Safely dispose engine connection pool during application shutdown."""
    await engine.dispose()
