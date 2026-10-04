from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_session
from app.models import Tenant, User
from app.schemas.auth_schemas import (
    TenantRegisterRequest,
    TenantRegisterResponse,
    LoginRequest,
    TokenResponse
)
from app.auth.security import get_password_hash, verify_password, create_access_token
import uuid

router = APIRouter()

@router.post("/register-tenant", response_model=TenantRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_tenant(req: TenantRegisterRequest, session: AsyncSession = Depends(get_session)):
    tenant = Tenant(name=req.tenant_name)
    session.add(tenant)
    await session.flush()
    
    result = await session.execute(select(User).where(User.email == req.admin_email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Email already registered"}}
        )
    
    hashed_password = get_password_hash(req.admin_password)
    user = User(
        tenant_id=tenant.id,
        email=req.admin_email,
        password_hash=hashed_password,
        role="admin"
    )
    session.add(user)
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(user)
    
    return TenantRegisterResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        admin_user_id=str(user.id),
        admin_email=user.email
    )

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(User, Tenant)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(User.email == req.email, Tenant.name == req.tenant_name)
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Incorrect email, password, or tenant"}}
        )
    user, tenant = row
    
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Incorrect email, password, or tenant"}}
        )
        
    access_token = create_access_token(
        data={"sub": str(user.id), "tenant_id": str(tenant.id), "role": user.role}
    )
    return TokenResponse(access_token=access_token, token_type="bearer")
