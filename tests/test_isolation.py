import asyncio
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import Dataset, Tenant, User

client = TestClient(app)

def test_tenant_isolation():
    r_a = client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Tenant A",
        "admin_email": "adminA@example.com",
        "admin_password": "pass"
    })
    assert r_a.status_code == 201
    tenant_a_id = r_a.json()["tenant_id"]

    r_b = client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Tenant B",
        "admin_email": "adminB@example.com",
        "admin_password": "pass"
    })
    assert r_b.status_code == 201

    login_b = client.post("/api/v1/auth/login", json={
        "tenant_name": "Tenant B",
        "email": "adminB@example.com",
        "password": "pass"
    })
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]

    async def create_dataset_a():
        async with SessionLocal() as session:
            ds = Dataset(tenant_id=tenant_a_id, name="Dataset A", source_type="reviews")
            session.add(ds)
            await session.commit()
            await session.refresh(ds)
            return str(ds.id)
            
    dataset_a_id = asyncio.run(create_dataset_a())

    r_read = client.get(
        f"/api/v1/datasets/{dataset_a_id}", 
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert r_read.status_code == 404, "Tenant B should not be able to read Tenant A's dataset"
