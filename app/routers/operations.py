from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_db
from app.models.clinical import AuditLog, Patient
from app.models.identity import User
from app.models.operations import (
    Appointment,
    CatalogItem,
    Invoice,
    MedicalConsultation,
    Medication,
    Professional,
)
from app.routers.auth import effective_permissions, get_current_user, require_permissions
from app.schemas.operations import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    CatalogItemCreate,
    CatalogItemResponse,
    CatalogItemUpdate,
    ConsultationCreate,
    ConsultationResponse,
    ConsultationUpdate,
    InvoiceCreate,
    InvoiceResponse,
    MedicationCreate,
    MedicationResponse,
    MedicationUpdate,
    PaymentRequest,
    ProfessionalCreate,
    ProfessionalResponse,
    ProfessionalUpdate,
    ReasonRequest,
    SpecialtyCreate,
    SpecialtyResponse,
)
from app.services import operations as service
from app.services import documents as document_service

professionals_router = APIRouter(prefix="/professionals", tags=["Profesionales"])
appointments_router = APIRouter(prefix="/appointments", tags=["Citas"])
consultations_router = APIRouter(prefix="/consultations", tags=["Consultas médicas"])
medications_router = APIRouter(prefix="/medications", tags=["Medicamentos"])
catalog_router = APIRouter(prefix="/catalog", tags=["Productos y servicios"])
invoices_router = APIRouter(prefix="/invoices", tags=["Facturación"])
audit_router = APIRouter(prefix="/audit", tags=["Auditoría"])
dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _service_error(error: Exception):
    if isinstance(error, service.MissingResource):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, service.ResourceConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise error


def _professional_response(professional: Professional) -> ProfessionalResponse:
    return ProfessionalResponse(
        id=professional.id,
        profession=professional.profession,
        registration_number=professional.registration_number,
        active=professional.active,
        person=professional.person,
        specialties=[specialty.name for specialty in professional.specialties],
    )


def _appointment_response(appointment: Appointment) -> AppointmentResponse:
    return AppointmentResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        professional_id=appointment.professional_id,
        start_at=appointment.start_at,
        end_at=appointment.end_at,
        status=appointment.status,
        reason=appointment.reason,
        created_by=appointment.created_by,
        updated_by=appointment.updated_by,
        confirmed_by=appointment.confirmed_by,
        cancelled_by=appointment.cancelled_by,
        cancelled_at=appointment.cancelled_at,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        patient_name=f"{appointment.patient.person.first_names} {appointment.patient.person.last_names}",
        professional_name=f"{appointment.professional.person.first_names} {appointment.professional.person.last_names}",
    )


def _consultation_response(consultation: MedicalConsultation) -> ConsultationResponse:
    return ConsultationResponse(
        id=consultation.id,
        appointment_id=consultation.appointment_id,
        professional_id=consultation.professional_id,
        reason=consultation.reason,
        diagnosis=consultation.diagnosis,
        observations=consultation.observations,
        treatment=consultation.treatment,
        notes=consultation.notes,
        weight=consultation.weight,
        height=consultation.height,
        temperature=consultation.temperature,
        heart_rate=consultation.heart_rate,
        respiratory_rate=consultation.respiratory_rate,
        oxygen_saturation=consultation.oxygen_saturation,
        blood_pressure_systolic=consultation.blood_pressure_systolic,
        blood_pressure_diastolic=consultation.blood_pressure_diastolic,
        created_at=consultation.created_at,
        voided_at=consultation.voided_at,
        void_reason=consultation.void_reason,
        medications=[
            {
                "medication_id": prescription.medication_id,
                "name": prescription.medication.name,
                "dose": prescription.dose,
                "frequency": prescription.frequency,
                "duration": prescription.duration,
                "route": prescription.route,
                "instructions": prescription.instructions,
            }
            for prescription in consultation.medications
        ],
    )


@dashboard_router.get("/summary")
async def get_dashboard_summary(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Debes cambiar tu contraseña antes de continuar")
    granted = effective_permissions(user)
    now = datetime.now(UTC)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    summary = {
        "patients_active": None,
        "appointments_today": None,
        "appointments_pending": None,
        "consultations_recent": None,
        "invoices_recent": None,
    }
    if "patients.read" in granted:
        summary["patients_active"] = await db.scalar(
            select(func.count(Patient.id)).where(Patient.active.is_(True))
        )
    if "appointments.read" in granted:
        summary["appointments_today"] = await db.scalar(select(func.count(Appointment.id)).where(
            Appointment.start_at >= start_of_day, Appointment.start_at < end_of_day
        ))
        summary["appointments_pending"] = await db.scalar(select(func.count(Appointment.id)).where(
            Appointment.status == "PENDING"
        ))
    if "medical_consultations.read" in granted:
        summary["consultations_recent"] = await db.scalar(select(func.count(MedicalConsultation.id)).where(
            MedicalConsultation.created_at >= now - timedelta(days=7)
        ))
    if "billing.read" in granted:
        summary["invoices_recent"] = await db.scalar(select(func.count(Invoice.id)).where(
            Invoice.created_at >= now - timedelta(days=7)
        ))
    return summary


@professionals_router.get("/specialties", response_model=list[SpecialtyResponse])
async def get_specialties(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.read"))],
):
    return await service.list_specialties(db)


@professionals_router.post("/specialties", response_model=SpecialtyResponse, status_code=201)
async def add_specialty(
    payload: SpecialtyCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.create"))],
):
    try:
        return await service.create_specialty(db, payload.name, user, request.client.host if request.client else None)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="La especialidad ya existe") from error


@professionals_router.get("/", response_model=list[ProfessionalResponse])
async def get_professionals(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.read"))],
    search: str | None = Query(default=None, max_length=120),
    active: bool | None = None,
):
    results = await service.list_professionals(db, search, active)
    return [_professional_response(professional) for professional in results]


@professionals_router.post("/", response_model=ProfessionalResponse, status_code=201)
async def add_professional(
    payload: ProfessionalCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.create"))],
):
    try:
        professional = await service.create_professional(
            db, payload, user, request.client.host if request.client else None
        )
        return _professional_response(professional)
    except (service.MissingResource, service.ResourceConflict) as error:
        _service_error(error)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Documento o registro profesional duplicado") from error


@professionals_router.post("/{professional_id}/deactivate", status_code=204)
async def disable_professional(
    professional_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.deactivate"))],
):
    professional = await db.scalar(select(Professional).where(Professional.id == professional_id))
    if professional is None:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    await service.deactivate_professional(db, professional, user, request.client.host if request.client else None)
    return Response(status_code=204)


@professionals_router.patch("/{professional_id}", response_model=ProfessionalResponse)
async def edit_professional(
    professional_id: int,
    payload: ProfessionalUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("professionals.update"))],
):
    professional = await db.scalar(
        select(Professional).options(selectinload(Professional.specialties)).where(Professional.id == professional_id)
    )
    if professional is None:
        raise HTTPException(status_code=404, detail="Profesional no encontrado")
    try:
        professional = await service.update_professional(
            db, professional, payload, user, request.client.host if request.client else None
        )
        return _professional_response(professional)
    except service.MissingResource as error:
        _service_error(error)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="El registro profesional ya existe") from error


@appointments_router.get("/", response_model=list[AppointmentResponse])
async def get_appointments(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("appointments.read"))],
    start: datetime | None = None,
    end: datetime | None = None,
    status_filter: str | None = Query(default=None, alias="status", pattern="^(PENDING|CONFIRMED|CANCELLED|COMPLETED)$"),
):
    appointments = await service.list_appointments(db, start, end, status_filter)
    return [_appointment_response(appointment) for appointment in appointments]


@appointments_router.post("/", response_model=AppointmentResponse, status_code=201)
async def add_appointment(
    payload: AppointmentCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("appointments.create"))],
):
    try:
        appointment = await service.create_appointment(db, payload, user, request.client.host if request.client else None)
        return _appointment_response(appointment)
    except (service.MissingResource, service.ResourceConflict) as error:
        _service_error(error)


@appointments_router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def edit_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("appointments.update"))],
):
    appointment = await service.get_appointment(db, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    try:
        appointment = await service.update_appointment(
            db, appointment, payload, user, request.client.host if request.client else None
        )
        return _appointment_response(appointment)
    except (service.MissingResource, service.ResourceConflict) as error:
        _service_error(error)


@appointments_router.post("/{appointment_id}/{action}", response_model=AppointmentResponse)
async def update_appointment_status(
    appointment_id: int,
    action: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("appointments.update"))],
):
    if action not in {"confirm", "cancel", "complete"}:
        raise HTTPException(status_code=404, detail="Acción no encontrada")
    action_permission = {
        "confirm": "appointments.confirm",
        "cancel": "appointments.cancel",
        "complete": "appointments.complete",
    }[action]
    if action_permission not in effective_permissions(user):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    appointment = await service.get_appointment(db, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    try:
        appointment = await service.transition_appointment(
            db, appointment, action, user, request.client.host if request.client else None
        )
        return _appointment_response(appointment)
    except service.ResourceConflict as error:
        _service_error(error)


@consultations_router.get("/", response_model=list[ConsultationResponse])
async def get_consultations(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_consultations.read"))],
    patient_id: int | None = None,
):
    consultations = await service.list_consultations(db, patient_id)
    return [_consultation_response(consultation) for consultation in consultations]


@consultations_router.get("/{consultation_id}/pdf")
async def export_consultation(
    consultation_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_history.export"))],
):
    try:
        content, _ = await document_service.render_consultation_pdf(db, user, consultation_id)
    except service.MissingResource as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=consultation-{consultation_id}.pdf"},
    )


@consultations_router.patch("/{consultation_id}", response_model=ConsultationResponse)
async def edit_consultation(
    consultation_id: int,
    payload: ConsultationUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_consultations.update"))],
):
    consultation = await service.get_consultation(db, consultation_id)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    try:
        consultation = await service.update_consultation(
            db, consultation, payload, user, request.client.host if request.client else None
        )
        return _consultation_response(consultation)
    except service.ResourceConflict as error:
        _service_error(error)


@consultations_router.post("/", response_model=ConsultationResponse, status_code=201)
async def add_consultation(
    payload: ConsultationCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_consultations.create"))],
):
    try:
        consultation = await service.create_consultation(
            db, payload, user, request.client.host if request.client else None
        )
        return _consultation_response(consultation)
    except (service.MissingResource, service.ResourceConflict) as error:
        _service_error(error)


@consultations_router.post("/{consultation_id}/void", status_code=204)
async def cancel_consultation(
    consultation_id: int,
    payload: ReasonRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_consultations.void"))],
):
    consultation = await db.scalar(
        select(MedicalConsultation).where(MedicalConsultation.id == consultation_id)
    )
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    try:
        await service.void_consultation(
            db, consultation, payload.reason, user, request.client.host if request.client else None
        )
    except service.ResourceConflict as error:
        _service_error(error)
    return Response(status_code=204)


@medications_router.get("/", response_model=list[MedicationResponse])
async def get_medications(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.read"))],
):
    return list((await db.scalars(select(Medication).where(Medication.active.is_(True)).order_by(Medication.name))).all())


@medications_router.post("/", response_model=MedicationResponse, status_code=201)
async def add_medication(
    payload: MedicationCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.create"))],
):
    return await service.create_medication(db, payload, user, request.client.host if request.client else None)


@medications_router.post("/{medication_id}/deactivate", status_code=204)
async def disable_medication(
    medication_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.deactivate"))],
):
    medication = await db.scalar(select(Medication).where(Medication.id == medication_id))
    if medication is None:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado")
    await service.deactivate_medication(db, medication, user, request.client.host if request.client else None)
    return Response(status_code=204)


@medications_router.patch("/{medication_id}", response_model=MedicationResponse)
async def edit_medication(
    medication_id: int,
    payload: MedicationUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.update"))],
):
    medication = await db.scalar(select(Medication).where(Medication.id == medication_id))
    if medication is None:
        raise HTTPException(status_code=404, detail="Medicamento no encontrado")
    return await service.update_medication(
        db, medication, payload, user, request.client.host if request.client else None
    )


@catalog_router.get("/", response_model=list[CatalogItemResponse])
async def get_catalog(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.read"))],
    item_type: str | None = Query(default=None, alias="type", pattern="^(PRODUCT|SERVICE)$"),
    active: bool | None = True,
):
    return await service.list_catalog(db, item_type, active)


@catalog_router.post("/", response_model=CatalogItemResponse, status_code=201)
async def add_catalog_item(
    payload: CatalogItemCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.create"))],
):
    return await service.create_catalog_item(db, payload, user, request.client.host if request.client else None)


@catalog_router.post("/{item_id}/deactivate", status_code=204)
async def disable_catalog_item(
    item_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.deactivate"))],
):
    item = await db.scalar(select(CatalogItem).where(CatalogItem.id == item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Producto o servicio no encontrado")
    await service.deactivate_catalog_item(db, item, user, request.client.host if request.client else None)
    return Response(status_code=204)


@catalog_router.patch("/{item_id}", response_model=CatalogItemResponse)
async def edit_catalog_item(
    item_id: int,
    payload: CatalogItemUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("products.update"))],
):
    item = await db.scalar(select(CatalogItem).where(CatalogItem.id == item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Producto o servicio no encontrado")
    return await service.update_catalog_item(
        db, item, payload, user, request.client.host if request.client else None
    )


@invoices_router.get("/", response_model=list[InvoiceResponse])
async def get_invoices(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("billing.read"))],
    patient_id: int | None = None,
):
    return await service.list_invoices(db, patient_id)


@invoices_router.post("/", response_model=InvoiceResponse, status_code=201)
async def add_invoice(
    payload: InvoiceCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("billing.create"))],
):
    try:
        return await service.create_invoice(db, payload, user, request.client.host if request.client else None)
    except (service.MissingResource, service.ResourceConflict) as error:
        _service_error(error)


@invoices_router.post("/{invoice_id}/paid", status_code=204)
async def pay_invoice(
    invoice_id: int,
    payload: PaymentRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("billing.update"))],
):
    invoice = await service.get_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    try:
        await service.mark_invoice_paid(db, invoice, payload.payment_method, user,
                                        request.client.host if request.client else None)
    except service.ResourceConflict as error:
        _service_error(error)
    return Response(status_code=204)


@invoices_router.post("/{invoice_id}/void", status_code=204)
async def cancel_invoice(
    invoice_id: int,
    payload: ReasonRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("billing.void"))],
):
    invoice = await service.get_invoice(db, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    try:
        await service.void_invoice(db, invoice, payload.reason, user,
                                   request.client.host if request.client else None)
    except service.ResourceConflict as error:
        _service_error(error)
    return Response(status_code=204)


@audit_router.get("/", response_model=list[dict])
async def get_audit_logs(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("audit.read"))],
    entity_type: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    rows = (await db.scalars(query)).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "timestamp": row.timestamp,
            "old_values": row.old_values,
            "new_values": row.new_values,
            "ip_address": row.ip_address,
        }
        for row in rows
    ]
