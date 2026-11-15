import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_dataset_upload_csv():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uid = uuid.uuid4().hex[:8]
        tenant_name = f"Upload_Tenant_{uid}"
        email = f"upload_{uid}@example.com"

        res = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": tenant_name,
            "admin_email": email,
            "admin_password": "pass"
        })
        assert res.status_code == 201

        login = await client.post("/api/v1/auth/login", json={
            "tenant_name": tenant_name,
            "email": email,
            "password": "pass"
        })
        assert login.status_code == 200
        token = login.json()["access_token"]

        csv_content = b"external_id,text,rating\n1,Great product!,5\n2,Bad product.,1\n"

        response = await client.post(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "Test CSV", "source_type": "reviews"},
            files={"file": ("test.csv", csv_content, "text/csv")}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test CSV"
        assert data["row_count"] == 2
        assert data["status"] == "uploaded"


@pytest.mark.anyio
async def test_dataset_upload_invalid_csv():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uid = uuid.uuid4().hex[:8]
        tenant_name = f"Invalid_Tenant_{uid}"
        email = f"invalid_{uid}@example.com"

        res = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": tenant_name,
            "admin_email": email,
            "admin_password": "pass"
        })
        assert res.status_code == 201

        login = await client.post("/api/v1/auth/login", json={
            "tenant_name": tenant_name,
            "email": email,
            "password": "pass"
        })
        assert login.status_code == 200
        token = login.json()["access_token"]

        csv_content = b"external_id,rating\n1,5\n"

        response = await client.post(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "Invalid CSV", "source_type": "reviews"},
            files={"file": ("invalid.csv", csv_content, "text/csv")}
        )

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["error"]["code"] == "validation_error"
        assert "bad_rows" in data["detail"]["error"]
