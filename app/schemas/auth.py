from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=72)


class ProfileUpdateRequest(BaseModel):
    first_names: str | None = Field(default=None, min_length=1, max_length=120)
    last_names: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    profile_photo: str | None = Field(default=None, max_length=500)

    @field_validator("first_names", "last_names", mode="before")
    @classmethod
    def required_names_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("El nombre y los apellidos no pueden ser nulos")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool


class PersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_names: str
    last_names: str
    document_type: str | None
    document_number: str | None
    birth_date: date | None
    phone: str | None
    email: str | None


class UserResponse(BaseModel):
    id: int
    username: str
    active: bool
    must_change_password: bool
    is_primary_admin: bool
    profile_photo: str | None
    roles: list[str]
    permissions: list[str]
    person: PersonResponse