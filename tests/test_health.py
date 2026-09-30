from fastapi.testclient import TestClient

from app.main import app
from app.routers import health

client = TestClient(app)


def _patch(monkeypatch, db: bool, redis: bool):
    async def _db():
        return db

    async def _redis():
        return redis

    monkeypatch.setattr(health, "check_db", _db)
    monkeypatch.setattr(health, "check_redis", _redis)


def test_health_ok(monkeypatch):
    _patch(monkeypatch, True, True)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "up", "redis": "up"}


def test_health_degraded_when_redis_down(monkeypatch):
    _patch(monkeypatch, True, False)
    r = client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json()["redis"] == "down"
