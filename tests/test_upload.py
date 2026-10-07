import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dataset_upload_csv():
    res = client.post("/api/v1/auth/register-tenant", json={
        "tenant_name": "Upload Tenant",
        "admin_email": "upload@example.com",
        "admin_password": "pass"
    })
    
    login = client.post("/api/v1/auth/login", json={
        "tenant_name": "Upload Tenant",
        "email": "upload@example.com",
        "password": "pass"
    })
    token = login.json()["access_token"]
    
    csv_content = b"external_id,text,rating\n1,Great product!,5\n2,Bad product.,1\n"
    
    response = client.post(
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

def test_dataset_upload_invalid_csv():
    login = client.post("/api/v1/auth/login", json={
        "tenant_name": "Upload Tenant",
        "email": "upload@example.com",
        "password": "pass"
    })
    token = login.json()["access_token"]
    
    csv_content = b"external_id,rating\n1,5\n"
    
    response = client.post(
        "/api/v1/datasets",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "Invalid CSV", "source_type": "reviews"},
        files={"file": ("invalid.csv", csv_content, "text/csv")}
    )
    
    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["error"]["code"] == "validation_error"
    assert "bad_rows" in data["detail"]["error"]
