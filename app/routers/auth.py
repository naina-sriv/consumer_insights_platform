import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_access_token, get_password_hash, verify_password
from app.db import get_session
from app.models import AuditLog, Tenant, User
from app.schemas.auth_schemas import (
    LoginRequest,
    TenantRegisterRequest,
    TenantRegisterResponse,
    TokenResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/register-tenant",
    response_model=TenantRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new tenant organization with primary admin",
)
async def register_tenant(
    req: TenantRegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    # Check if tenant name already exists
    existing_tenant = await session.execute(
        select(Tenant).where(Tenant.name == req.tenant_name)
    )
    if existing_tenant.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Tenant name already taken"}},
        )

    # Check if email is already registered
    existing_user = await session.execute(
        select(User).where(User.email == req.admin_email)
    )
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Email already registered"}},
        )

    # Provision tenant
    tenant = Tenant(name=req.tenant_name)
    session.add(tenant)
    await session.flush()

    # Provision admin user
    hashed_password = get_password_hash(req.admin_password)
    user = User(
        tenant_id=tenant.id,
        email=req.admin_email,
        password_hash=hashed_password,
        role="admin",
    )
    session.add(user)
    await session.flush()

    # Append audit log
    audit = AuditLog(
        tenant_id=tenant.id,
        user_id=user.id,
        action="tenant.registered",
        entity_type="tenant",
        entity_id=tenant.id,
        detail={"tenant_name": tenant.name, "admin_email": user.email},
    )
    session.add(audit)
    await session.commit()

    logger.info("Successfully registered tenant %s (id=%s)", tenant.name, tenant.id)

    return TenantRegisterResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        admin_user_id=str(user.id),
        admin_email=user.email,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and issue JWT bearer token",
)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(User, Tenant)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(User.email == req.email, Tenant.name == req.tenant_name)
    )
    result = await session.execute(query)
    row = result.first()

    invalid_credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthorized", "message": "Incorrect email, password, or tenant"}},
    )

    if not row:
        raise invalid_credentials_exc

    user, tenant = row

    if not verify_password(req.password, user.password_hash):
        raise invalid_credentials_exc

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "tenant_id": str(tenant.id),
            "role": user.role,
        }
    )

    return TokenResponse(access_token=access_token, token_type="bearer")
