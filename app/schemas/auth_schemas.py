from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantRegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_name: str = Field(..., min_length=2, max_length=100, description="Unique tenant or organization name")
    admin_email: EmailStr = Field(..., description="Initial administrator email address")
    admin_password: str = Field(..., min_length=4, max_length=128, description="Administrator password")


class TenantRegisterResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    admin_user_id: str
    admin_email: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_name: str = Field(..., description="Tenant organization name")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
