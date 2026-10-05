from pydantic import BaseModel, Field, field_validator

from app.schemas.patients import PersonCreate


class UserCreate(BaseModel):
    person: PersonCreate
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=72)
    role_ids: list[int] = []

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña excede el máximo admitido")
        return value


class UserUpdate(BaseModel):
    active: bool | None = None
    role_ids: list[int] | None = None


class UserAdminResponse(BaseModel):
    id: int
    username: str
    active: bool
    must_change_password: bool
    is_primary_admin: bool
    roles: list[str]
    permissions: list[str]
    first_names: str
    last_names: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=250)
    permission_codes: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=250)
    active: bool | None = None
    permission_codes: list[str] | None = None


class PermissionResponse(BaseModel):
    id: int
    code: str
    description: str | None


class PermissionOverrideInput(BaseModel):
    code: str
    granted: bool


class UserPermissionOverridesUpdate(BaseModel):
    overrides: list[PermissionOverrideInput]
