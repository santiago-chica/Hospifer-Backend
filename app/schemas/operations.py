from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.patients import PatientPersonResponse, PersonCreate


class ProfessionalCreate(BaseModel):
    person: PersonCreate
    profession: str = Field(min_length=1, max_length=120)
    registration_number: str | None = Field(default=None, max_length=100)
    specialty_ids: list[int] = []


class ProfessionalResponse(BaseModel):
    id: int
    profession: str
    registration_number: str | None
    active: bool
    person: PatientPersonResponse
    specialties: list[str]


class ProfessionalUpdate(BaseModel):
    profession: str | None = Field(default=None, min_length=1, max_length=120)
    registration_number: str | None = Field(default=None, max_length=100)
    specialty_ids: list[int] | None = None


class SpecialtyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class SpecialtyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    active: bool


class AppointmentCreate(BaseModel):
    patient_id: int
    professional_id: int
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.start_at >= self.end_at:
            raise ValueError("start_at debe ser anterior a end_at")
        return self


class AppointmentUpdate(BaseModel):
    patient_id: int | None = None
    professional_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=500)


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    professional_id: int
    start_at: datetime
    end_at: datetime
    status: str
    reason: str | None
    created_by: int | None
    updated_by: int | None
    confirmed_by: int | None
    cancelled_by: int | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    patient_name: str
    professional_name: str


class PrescriptionCreate(BaseModel):
    medication_id: int
    dose: str = Field(min_length=1, max_length=120)
    frequency: str = Field(min_length=1, max_length=180)
    duration: str = Field(min_length=1, max_length=120)
    route: str = Field(min_length=1, max_length=80)
    instructions: str | None = Field(default=None, max_length=4000)


class ConsultationCreate(BaseModel):
    appointment_id: int
    professional_id: int
    reason: str | None = None
    diagnosis: str | None = None
    observations: str | None = None
    treatment: str | None = None
    notes: str | None = None
    weight: Decimal | None = Field(default=None, gt=0, le=1000)
    height: Decimal | None = Field(default=None, gt=0, le=300)
    temperature: Decimal | None = Field(default=None, ge=25, le=45)
    heart_rate: int | None = Field(default=None, gt=0, le=300)
    respiratory_rate: int | None = Field(default=None, gt=0, le=100)
    oxygen_saturation: Decimal | None = Field(default=None, ge=0, le=100)
    blood_pressure_systolic: int | None = Field(default=None, gt=0, le=350)
    blood_pressure_diastolic: int | None = Field(default=None, gt=0, le=250)
    medications: list[PrescriptionCreate] = []


class ConsultationUpdate(BaseModel):
    reason: str | None = None
    diagnosis: str | None = None
    observations: str | None = None
    treatment: str | None = None
    notes: str | None = None
    weight: Decimal | None = Field(default=None, gt=0, le=1000)
    height: Decimal | None = Field(default=None, gt=0, le=300)
    temperature: Decimal | None = Field(default=None, ge=25, le=45)
    heart_rate: int | None = Field(default=None, gt=0, le=300)
    respiratory_rate: int | None = Field(default=None, gt=0, le=100)
    oxygen_saturation: Decimal | None = Field(default=None, ge=0, le=100)
    blood_pressure_systolic: int | None = Field(default=None, gt=0, le=350)
    blood_pressure_diastolic: int | None = Field(default=None, gt=0, le=250)


class ConsultationResponse(BaseModel):
    id: int
    appointment_id: int
    professional_id: int
    reason: str | None
    diagnosis: str | None
    observations: str | None
    treatment: str | None
    notes: str | None
    weight: Decimal | None
    height: Decimal | None
    temperature: Decimal | None
    heart_rate: int | None
    respiratory_rate: int | None
    oxygen_saturation: Decimal | None
    blood_pressure_systolic: int | None
    blood_pressure_diastolic: int | None
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    medications: list[dict]


class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    active_ingredient: str | None = Field(default=None, max_length=180)
    presentation: str | None = Field(default=None, max_length=180)
    description: str | None = None


class MedicationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    active_ingredient: str | None = Field(default=None, max_length=180)
    presentation: str | None = Field(default=None, max_length=180)
    description: str | None = None


class MedicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    active_ingredient: str | None
    presentation: str | None
    description: str | None
    active: bool


class CatalogItemCreate(BaseModel):
    item_type: Literal["PRODUCT", "SERVICE"]
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    active_ingredient: str | None = Field(default=None, max_length=180)
    presentation: str | None = Field(default=None, max_length=180)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CatalogItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    active_ingredient: str | None = Field(default=None, max_length=180)
    presentation: str | None = Field(default=None, max_length=180)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class CatalogItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    name: str
    description: str | None
    active_ingredient: str | None
    presentation: str | None
    unit_price: Decimal
    active: bool


class InvoiceLineCreate(BaseModel):
    catalog_item_id: int
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class InvoiceCreate(BaseModel):
    patient_id: int
    professional_id: int | None = None
    appointment_id: int | None = None
    consultation_id: int | None = None
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    payment_method: str | None = Field(default=None, max_length=40)
    items: list[InvoiceLineCreate] = Field(min_length=1)


class InvoiceItemResponse(BaseModel):
    id: int
    catalog_item_id: int | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal


class InvoiceResponse(BaseModel):
    id: int
    patient_id: int
    professional_id: int | None
    appointment_id: int | None
    consultation_id: int | None
    status: str
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    payment_method: str | None
    payment_status: str
    created_at: datetime
    items: list[InvoiceItemResponse]


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PaymentRequest(BaseModel):
    payment_method: str = Field(min_length=2, max_length=40)
