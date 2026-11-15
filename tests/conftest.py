import pytest
from app.db import engine


@pytest.fixture(autouse=True)
def cleanup_db_pool():
    yield
    engine.sync_engine.dispose()
