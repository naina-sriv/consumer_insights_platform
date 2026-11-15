import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import SessionLocal
from app.models import Dataset


@pytest.mark.anyio
async def test_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uid_a = uuid.uuid4().hex[:8]
        uid_b = uuid.uuid4().hex[:8]

        r_a = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant_{uid_a}",
            "admin_email": f"admin_{uid_a}@example.com",
            "admin_password": "pass"
        })
        assert r_a.status_code == 201
        tenant_a_id = r_a.json()["tenant_id"]

        r_b = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant_{uid_b}",
            "admin_email": f"admin_{uid_b}@example.com",
            "admin_password": "pass"
        })
        assert r_b.status_code == 201

        login_b = await client.post("/api/v1/auth/login", json={
            "tenant_name": f"Tenant_{uid_b}",
            "email": f"admin_{uid_b}@example.com",
            "password": "pass"
        })
        assert login_b.status_code == 200
        token_b = login_b.json()["access_token"]

        async with SessionLocal() as session:
            ds = Dataset(tenant_id=tenant_a_id, name="Dataset A", source_type="reviews")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)
            dataset_a_id = str(ds.id)

        r_read = await client.get(
            f"/api/v1/datasets/{dataset_a_id}",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert r_read.status_code == 404, "Tenant B should not be able to read Tenant A's dataset"
