import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db import SessionLocal
from app.models import Tenant, Dataset, Record, Job, AuditLog
from app.worker.tasks import execute_job_lifecycle


@pytest.mark.anyio
async def test_create_job_and_idempotency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uid = uuid.uuid4().hex[:8]
        tenant_name = f"JobTenant_{uid}"
        email = f"job_admin_{uid}@example.com"

        reg = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": tenant_name,
            "admin_email": email,
            "admin_password": "pass"
        })
        assert reg.status_code == 201
        tenant_id = reg.json()["tenant_id"]

        login = await client.post("/api/v1/auth/login", json={
            "tenant_name": tenant_name,
            "email": email,
            "password": "pass"
        })
        assert login.status_code == 200
        token = login.json()["access_token"]

        async with SessionLocal() as session:
            ds = Dataset(
                tenant_id=uuid.UUID(tenant_id),
                name="Job Dataset",
                source_type="reviews",
                status="uploaded"
            )
            session.add(ds)
            await session.commit()
            await session.refresh(ds)
            dataset_id = str(ds.id)

        idempotency_key = f"key_{uid}"
        r1 = await client.post(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "dataset_id": dataset_id,
                "type": "analyze",
                "idempotency_key": idempotency_key
            }
        )
        assert r1.status_code == 202
        data1 = r1.json()
        assert data1["status"] == "queued"
        job_id = data1["id"]

        r2 = await client.post(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "dataset_id": dataset_id,
                "type": "analyze",
                "idempotency_key": idempotency_key
            }
        )
        assert r2.status_code == 202
        data2 = r2.json()
        assert data2["id"] == job_id

        r_get = await client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert r_get.status_code == 200
        get_data = r_get.json()
        assert get_data["id"] == job_id
        assert get_data["status"] == "queued"
        assert get_data["progress"] == 0


@pytest.mark.anyio
async def test_job_tenant_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        uid_a = uuid.uuid4().hex[:8]
        uid_b = uuid.uuid4().hex[:8]

        r_a = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"TenantA_{uid_a}",
            "admin_email": f"admin_{uid_a}@example.com",
            "admin_password": "pass"
        })
        assert r_a.status_code == 201
        tenant_a_id = r_a.json()["tenant_id"]

        r_b = await client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"TenantB_{uid_b}",
            "admin_email": f"admin_{uid_b}@example.com",
            "admin_password": "pass"
        })
        assert r_b.status_code == 201

        login_b = await client.post("/api/v1/auth/login", json={
            "tenant_name": f"TenantB_{uid_b}",
            "email": f"admin_{uid_b}@example.com",
            "password": "pass"
        })
        token_b = login_b.json()["access_token"]

        async with SessionLocal() as session:
            ds = Dataset(
                tenant_id=uuid.UUID(tenant_a_id),
                name="Dataset A",
                source_type="reviews"
            )
            session.add(ds)
            await session.flush()

            job_a = Job(
                tenant_id=uuid.UUID(tenant_a_id),
                dataset_id=ds.id,
                type="analyze",
                status="queued"
            )
            session.add(job_a)
            await session.commit()
            await session.refresh(job_a)
            job_a_id = str(job_a.id)

        r_read = await client.get(
            f"/api/v1/jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert r_read.status_code == 404
        assert r_read.json()["detail"]["error"]["code"] == "not_found"


@pytest.mark.anyio
async def test_job_execution_progress_and_completion():
    uid = uuid.uuid4().hex[:8]

    async with SessionLocal() as session:
        tenant = Tenant(name=f"Progress_Tenant_{uid}")
        session.add(tenant)
        await session.flush()
        tenant_id = tenant.id

        ds = Dataset(
            tenant_id=tenant_id,
            name=f"Dataset_{uid}",
            source_type="reviews"
        )
        session.add(ds)
        await session.flush()

        records = [
            Record(
                tenant_id=tenant_id,
                dataset_id=ds.id,
                external_id=f"ext_{i}",
                text=f"Sample feedback text {i}"
            )
            for i in range(120)
        ]
        session.add_all(records)
        ds.row_count = 120

        job = Job(
            tenant_id=tenant_id,
            dataset_id=ds.id,
            type="analyze",
            status="queued"
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = str(job.id)

    success = await execute_job_lifecycle(job_id)
    assert success is True

    async with SessionLocal() as session:
        res = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        updated_job = res.scalar_one()
        assert updated_job.status == "completed"
        assert updated_job.progress == 100
        assert updated_job.finished_at is not None

        audit_res = await session.execute(
            select(AuditLog).where(AuditLog.entity_id == uuid.UUID(job_id))
        )
        audit_entries = audit_res.scalars().all()
        actions = [a.action for a in audit_entries]
        assert "job.running" in actions
        assert "job.completed" in actions


@pytest.mark.anyio
async def test_forced_failure_retries_3_times_then_fails():
    uid = uuid.uuid4().hex[:8]

    async with SessionLocal() as session:
        tenant = Tenant(name=f"Fail_Tenant_{uid}")
        session.add(tenant)
        await session.flush()
        tenant_id = tenant.id

        ds = Dataset(
            tenant_id=tenant_id,
            name=f"Fail_Dataset_{uid}",
            source_type="reviews"
        )
        session.add(ds)
        await session.flush()

        job = Job(
            tenant_id=tenant_id,
            dataset_id=ds.id,
            type="analyze",
            status="queued"
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = str(job.id)

    success = await execute_job_lifecycle(
        job_id=job_id,
        force_failure=True,
        backoff_delays=[0.01, 0.02, 0.03],
        max_attempts=3
    )
    assert success is False

    async with SessionLocal() as session:
        res = await session.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        failed_job = res.scalar_one()

        assert failed_job.status == "failed"
        assert failed_job.attempts == 3
        assert "Simulated provider timeout" in (failed_job.error or "")
        assert failed_job.finished_at is not None

        audit_res = await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == uuid.UUID(job_id))
            .order_by(AuditLog.created_at)
        )
        audit_entries = audit_res.scalars().all()
        actions = [a.action for a in audit_entries]

        assert actions.count("job.running") == 3
        assert actions.count("job.retrying") == 2
        assert actions.count("job.failed") == 1
