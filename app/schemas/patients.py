from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BackgroundCategory = Literal[
    "ALERGIA", "ENFERMEDAD", "CIRUGIA", "ANTECEDENTE_FAMILIAR", "MEDICAMENTO", "OTRO"
]


class PersonCreate(BaseModel):
    first_names: str = Field(min_length=1, max_length=120)
    last_names: str = Field(min_length=1, max_length=120)
    document_type: str | None = Field(default=None, max_length=30)
    document_number: str | None = Field(default=None, max_length=60)
    birth_date: date | None = None
    sex: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)


class PersonUpdate(BaseModel):
    first_names: str | None = Field(default=None, min_length=1, max_length=120)
    last_names: str | None = Field(default=None, min_length=1, max_length=120)
    document_type: str | None = Field(default=None, max_length=30)
    document_number: str | None = Field(default=None, max_length=60)
    birth_date: date | None = None
    sex: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)

    @field_validator("first_names", "last_names", mode="before")
    @classmethod
    def required_names_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("El nombre y los apellidos no pueden ser nulos")
        return value


class PatientCreate(BaseModel):
    person: PersonCreate


class PatientPersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_names: str
    last_names: str
    document_type: str | None
    document_number: str | None
    birth_date: date | None


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool
    created_at: datetime
    updated_at: datetime
    person: PatientPersonResponse


class PatientContactResponse(BaseModel):
    phone: str | None
    email: str | None
    address: str | None
    city: str | None


class BackgroundCreate(BaseModel):
    category: BackgroundCategory
    description: str = Field(min_length=1, max_length=4000)
    occurred_on: date | None = None
    observations: str | None = Field(default=None, max_length=4000)


class BackgroundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    description: str
    occurred_on: date | None
    observations: str | None
    active: bool
    created_at: datetime
    updated_at: datetime