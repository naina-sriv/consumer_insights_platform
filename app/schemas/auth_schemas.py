from pydantic import BaseModel, EmailStr
from typing import Optional
import uuid

class TenantRegisterRequest(BaseModel):
    tenant_name: str
    admin_email: EmailStr
    admin_password: str

class TenantRegisterResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    admin_user_id: str
    admin_email: str

class LoginRequest(BaseModel):
    tenant_name: str
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"