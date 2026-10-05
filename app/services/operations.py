from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinical import AuditLog, Patient
from app.models.identity import Person, User
from app.models.operations import (
    Appointment,
    CatalogItem,
    ConsultationMedication,
    Invoice,
    InvoiceItem,
    MedicalConsultation,
    Medication,
    Professional,
    Specialty,
)
from app.schemas.operations import (
    AppointmentCreate,
    AppointmentUpdate,
    CatalogItemCreate,
    CatalogItemUpdate,
    ConsultationCreate,
    ConsultationUpdate,
    InvoiceCreate,
    MedicationCreate,
    MedicationUpdate,
    ProfessionalCreate,
    ProfessionalUpdate,
)


class ResourceConflict(Exception):
    pass


class MissingResource(Exception):
    pass


def record_audit(
    db: AsyncSession,
    user: User,
    action: str,
    entity_type: str,
    entity_id: int,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        user_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=jsonable_encoder(old_values) if old_values is not None else None,
        new_values=jsonable_encoder(new_values) if new_values is not None else None,
        ip_address=ip_address,
    ))


async def list_professionals(db: AsyncSession, search: str | None, active: bool | None):
    query = select(Professional).options(
        selectinload(Professional.person), selectinload(Professional.specialties)
    ).order_by(Professional.id.desc())
    if active is not None:
        query = query.where(Professional.active.is_(active))
    if search:
        term = f"%{search.strip()}%"
        query = query.join(Professional.person).where(
            Person.first_names.ilike(term)
            | Person.last_names.ilike(term)
            | Person.document_number.ilike(term)
        )
    return list((await db.scalars(query)).all())


async def create_professional(db: AsyncSession, payload: ProfessionalCreate, user: User, ip: str | None):
    specialties = list((await db.scalars(
        select(Specialty).where(Specialty.id.in_(payload.specialty_ids), Specialty.active.is_(True))
    )).all()) if payload.specialty_ids else []
    if len(specialties) != len(set(payload.specialty_ids)):
        raise MissingResource("Una o más especialidades no existen o están inactivas")
    person = Person(**payload.person.model_dump())
    professional = Professional(
        person=person,
        profession=payload.profession,
        registration_number=payload.registration_number,
        specialties=specialties,
    )
    db.add(professional)
    await db.flush()
    record_audit(
        db, user, "professionals.create", "professional", professional.id,
        new_values={"profession": professional.profession, "specialty_ids": payload.specialty_ids},
        ip_address=ip,
    )
    await db.commit()
    return await db.scalar(
        select(Professional).options(
            selectinload(Professional.person), selectinload(Professional.specialties)
        ).where(Professional.id == professional.id)
    )


async def list_specialties(db: AsyncSession):
    return list((await db.scalars(select(Specialty).where(Specialty.active.is_(True)).order_by(Specialty.name))).all())


async def create_specialty(db: AsyncSession, name: str, user: User, ip: str | None):
    specialty = Specialty(name=name)
    db.add(specialty)
    await db.flush()
    record_audit(db, user, "specialties.create", "specialty", specialty.id, new_values={"name": name}, ip_address=ip)
    await db.commit()
    await db.refresh(specialty)
    return specialty


async def deactivate_professional(db: AsyncSession, professional: Professional, user: User, ip: str | None):
    professional.active = False
    record_audit(db, user, "professionals.deactivate", "professional", professional.id,
                 {"active": True}, {"active": False}, ip)
    await db.commit()


async def update_professional(
    db: AsyncSession, professional: Professional, payload: ProfessionalUpdate, user: User, ip: str | None
):
    changes = payload.model_dump(exclude_unset=True)
    old_values = {key: getattr(professional, key) for key in changes if key != "specialty_ids"}
    if "specialty_ids" in changes:
        specialty_ids = changes.pop("specialty_ids") or []
        specialties = list((await db.scalars(
            select(Specialty).where(Specialty.id.in_(specialty_ids), Specialty.active.is_(True))
        )).all()) if specialty_ids else []
        if len(specialties) != len(set(specialty_ids)):
            raise MissingResource("Una o más especialidades no existen o están inactivas")
        old_values["specialties"] = [item.name for item in professional.specialties]
        professional.specialties = specialties
        changes["specialty_ids"] = specialty_ids
    for field, value in changes.items():
        if field != "specialty_ids":
            setattr(professional, field, value)
    record_audit(db, user, "professionals.update", "professional", professional.id,
                 old_values, changes, ip)
    await db.commit()
    return await db.scalar(select(Professional).options(
        selectinload(Professional.person), selectinload(Professional.specialties)
    ).where(Professional.id == professional.id))


async def _appointment_query():
    return select(Appointment).options(
        selectinload(Appointment.patient).selectinload(Patient.person),
        selectinload(Appointment.professional).selectinload(Professional.person),
    )


async def list_appointments(db: AsyncSession, start: datetime | None, end: datetime | None, status_filter: str | None):
    query = await _appointment_query()
    if start is not None:
        query = query.where(Appointment.start_at >= start)
    if end is not None:
        query = query.where(Appointment.start_at < end)
    if status_filter:
        query = query.where(Appointment.status == status_filter)
    return list((await db.scalars(query.order_by(Appointment.start_at).limit(200))).all())


async def get_appointment(db: AsyncSession, appointment_id: int):
    query = await _appointment_query()
    return await db.scalar(query.where(Appointment.id == appointment_id))


async def _validate_appointment(
    db: AsyncSession,
    patient_id: int,
    professional_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_id: int | None = None,
):
    comparable_start = start_at if start_at.tzinfo else start_at.replace(tzinfo=UTC)
    comparable_end = end_at if end_at.tzinfo else end_at.replace(tzinfo=UTC)
    if comparable_start >= comparable_end:
        raise ResourceConflict("start_at debe ser anterior a end_at")
    patient = await db.scalar(select(Patient).where(Patient.id == patient_id, Patient.active.is_(True)))
    professional = await db.scalar(
        select(Professional).where(Professional.id == professional_id, Professional.active.is_(True))
    )
    if patient is None or professional is None:
        raise MissingResource("Paciente o profesional inexistente/inactivo")
    overlap_query = select(Appointment.id).where(
        Appointment.professional_id == professional_id,
        Appointment.status.in_(("PENDING", "CONFIRMED")),
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_id is not None:
        overlap_query = overlap_query.where(Appointment.id != exclude_id)
    if await db.scalar(overlap_query.limit(1)) is not None:
        raise ResourceConflict("El profesional ya tiene una cita en ese horario")


async def create_appointment(db: AsyncSession, payload: AppointmentCreate, user: User, ip: str | None):
    await _validate_appointment(
        db, payload.patient_id, payload.professional_id, payload.start_at, payload.end_at
    )
    appointment = Appointment(**payload.model_dump(), created_by=user.id)
    db.add(appointment)
    await db.flush()
    record_audit(db, user, "appointments.create", "appointment", appointment.id,
                 new_values=payload.model_dump(mode="json"), ip_address=ip)
    await db.commit()
    return await get_appointment(db, appointment.id)


async def update_appointment(
    db: AsyncSession, appointment: Appointment, payload: AppointmentUpdate, user: User, ip: str | None
):
    if appointment.status in {"CANCELLED", "COMPLETED"}:
        raise ResourceConflict("No se puede modificar una cita cancelada o completada")
    changes = payload.model_dump(exclude_unset=True)
    values = {
        "patient_id": changes.get("patient_id", appointment.patient_id),
        "professional_id": changes.get("professional_id", appointment.professional_id),
        "start_at": changes.get("start_at", appointment.start_at),
        "end_at": changes.get("end_at", appointment.end_at),
    }
    await _validate_appointment(db, **values, exclude_id=appointment.id)
    old_values = {key: getattr(appointment, key) for key in changes}
    for key, value in changes.items():
        setattr(appointment, key, value)
    appointment.updated_by = user.id
    record_audit(db, user, "appointments.update", "appointment", appointment.id,
                 old_values, changes, ip)
    await db.commit()
    return await get_appointment(db, appointment.id)


async def transition_appointment(
    db: AsyncSession, appointment: Appointment, action: str, user: User, ip: str | None
):
    transitions = {
        "confirm": {"PENDING": "CONFIRMED"},
        "cancel": {"PENDING": "CANCELLED", "CONFIRMED": "CANCELLED"},
        "complete": {"CONFIRMED": "COMPLETED"},
    }
    next_status = transitions.get(action, {}).get(appointment.status)
    if next_status is None:
        raise ResourceConflict(f"No se puede {action} una cita en estado {appointment.status}")
    old_status = appointment.status
    appointment.status = next_status
    appointment.updated_by = user.id
    if action == "confirm":
        appointment.confirmed_by = user.id
    if action == "cancel":
        appointment.cancelled_by = user.id
        appointment.cancelled_at = datetime.now(UTC)
    record_audit(db, user, f"appointments.{action}", "appointment", appointment.id,
                 {"status": old_status}, {"status": next_status}, ip)
    await db.commit()
    return await get_appointment(db, appointment.id)


async def create_consultation(db: AsyncSession, payload: ConsultationCreate, user: User, ip: str | None):
    appointment = await db.scalar(
        select(Appointment).where(Appointment.id == payload.appointment_id)
    )
    if appointment is None:
        raise MissingResource("Cita no encontrada")
    if appointment.professional_id != payload.professional_id:
        raise ResourceConflict("El profesional de la consulta debe coincidir con el de la cita")
    if appointment.status not in {"CONFIRMED", "COMPLETED"}:
        raise ResourceConflict("La cita debe estar confirmada antes de registrar la consulta")
    medication_ids = [item.medication_id for item in payload.medications]
    medications = list((await db.scalars(
        select(Medication).where(Medication.id.in_(medication_ids), Medication.active.is_(True))
    )).all()) if medication_ids else []
    if len(medications) != len(set(medication_ids)):
        raise MissingResource("Un medicamento no existe o está inactivo")
    values = payload.model_dump(exclude={"medications"})
    consultation = MedicalConsultation(**values, created_by=user.id)
    db.add(consultation)
    await db.flush()
    for prescription in payload.medications:
        db.add(ConsultationMedication(consultation_id=consultation.id, **prescription.model_dump()))
    record_audit(db, user, "medical_consultations.create", "medical_consultation", consultation.id,
                 new_values=payload.model_dump(mode="json"), ip_address=ip)
    await db.commit()
    return await get_consultation(db, consultation.id)


async def get_consultation(db: AsyncSession, consultation_id: int):
    return await db.scalar(
        select(MedicalConsultation).options(
            selectinload(MedicalConsultation.medications).selectinload(ConsultationMedication.medication)
        ).where(MedicalConsultation.id == consultation_id)
    )


async def list_consultations(db: AsyncSession, patient_id: int | None):
    query = select(MedicalConsultation).options(
        selectinload(MedicalConsultation.medications).selectinload(ConsultationMedication.medication),
        selectinload(MedicalConsultation.appointment),
    )
    if patient_id is not None:
        query = query.join(Appointment).where(Appointment.patient_id == patient_id)
    return list((await db.scalars(query.order_by(MedicalConsultation.created_at.desc()).limit(200))).all())


async def void_consultation(db: AsyncSession, consultation: MedicalConsultation, reason: str, user: User, ip: str | None):
    if consultation.voided_at is not None:
        raise ResourceConflict("La consulta ya está anulada")
    consultation.voided_at = datetime.now(UTC)
    consultation.voided_by = user.id
    consultation.void_reason = reason
    record_audit(db, user, "medical_consultations.void", "medical_consultation", consultation.id,
                 {"voided_at": None}, {"voided_at": consultation.voided_at, "void_reason": reason}, ip)
    await db.commit()


async def update_consultation(
    db: AsyncSession,
    consultation: MedicalConsultation,
    payload: ConsultationUpdate,
    user: User,
    ip: str | None,
):
    if consultation.voided_at is not None:
        raise ResourceConflict("No se puede editar una consulta anulada")
    changes = payload.model_dump(exclude_unset=True)
    old_values = {field: getattr(consultation, field) for field in changes}
    for field, value in changes.items():
        setattr(consultation, field, value)
    consultation.updated_by = user.id
    record_audit(db, user, "medical_consultations.update", "medical_consultation",
                 consultation.id, old_values, changes, ip)
    await db.commit()
    return await get_consultation(db, consultation.id)


async def create_medication(db: AsyncSession, payload: MedicationCreate, user: User, ip: str | None):
    medication = Medication(**payload.model_dump())
    db.add(medication)
    await db.flush()
    record_audit(db, user, "medications.create", "medication", medication.id,
                 new_values=payload.model_dump(), ip_address=ip)
    await db.commit()
    await db.refresh(medication)
    return medication


async def update_medication(
    db: AsyncSession, medication: Medication, payload: MedicationUpdate, user: User, ip: str | None
):
    changes = payload.model_dump(exclude_unset=True)
    old_values = {key: getattr(medication, key) for key in changes}
    for key, value in changes.items():
        setattr(medication, key, value)
    record_audit(db, user, "medications.update", "medication", medication.id,
                 old_values, changes, ip)
    await db.commit()
    await db.refresh(medication)
    return medication


async def deactivate_medication(db: AsyncSession, medication: Medication, user: User, ip: str | None):
    medication.active = False
    record_audit(db, user, "medications.deactivate", "medication", medication.id,
                 {"active": True}, {"active": False}, ip)
    await db.commit()


async def list_catalog(db: AsyncSession, item_type: str | None, active: bool | None):
    query = select(CatalogItem).order_by(CatalogItem.name)
    if item_type:
        query = query.where(CatalogItem.item_type == item_type)
    if active is not None:
        query = query.where(CatalogItem.active.is_(active))
    return list((await db.scalars(query.limit(300))).all())


async def create_catalog_item(db: AsyncSession, payload: CatalogItemCreate, user: User, ip: str | None):
    item = CatalogItem(**payload.model_dump())
    db.add(item)
    await db.flush()
    record_audit(db, user, "products.create", "catalog_item", item.id,
                 new_values=payload.model_dump(mode="json"), ip_address=ip)
    await db.commit()
    await db.refresh(item)
    return item


async def update_catalog_item(
    db: AsyncSession, item: CatalogItem, payload: CatalogItemUpdate, user: User, ip: str | None
):
    changes = payload.model_dump(exclude_unset=True)
    old_values = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    record_audit(db, user, "products.update", "catalog_item", item.id,
                 old_values, changes, ip)
    await db.commit()
    await db.refresh(item)
    return item


async def deactivate_catalog_item(db: AsyncSession, item: CatalogItem, user: User, ip: str | None):
    item.active = False
    record_audit(db, user, "products.deactivate", "catalog_item", item.id,
                 {"active": True}, {"active": False}, ip)
    await db.commit()


async def create_invoice(db: AsyncSession, payload: InvoiceCreate, user: User, ip: str | None):
    patient = await db.scalar(select(Patient).where(Patient.id == payload.patient_id))
    if patient is None:
        raise MissingResource("Paciente no encontrado")
    if payload.professional_id is not None:
        professional = await db.scalar(
            select(Professional).where(Professional.id == payload.professional_id)
        )
        if professional is None:
            raise MissingResource("Profesional no encontrado")
    if payload.appointment_id is not None:
        appointment = await db.scalar(
            select(Appointment).where(Appointment.id == payload.appointment_id)
        )
        if appointment is None:
            raise MissingResource("Cita no encontrada")
        if appointment.patient_id != payload.patient_id:
            raise ResourceConflict("La cita no corresponde al paciente de la factura")
    if payload.consultation_id is not None:
        consultation_patient_id = await db.scalar(
            select(Appointment.patient_id)
            .select_from(MedicalConsultation)
            .join(Appointment, Appointment.id == MedicalConsultation.appointment_id)
            .where(MedicalConsultation.id == payload.consultation_id)
        )
        if consultation_patient_id is None:
            raise MissingResource("Consulta no encontrada")
        if consultation_patient_id != payload.patient_id:
            raise ResourceConflict("La consulta no corresponde al paciente de la factura")
    catalog_ids = {line.catalog_item_id for line in payload.items}
    catalog = {
        item.id: item
        for item in (await db.scalars(select(CatalogItem).where(
            CatalogItem.id.in_(catalog_ids), CatalogItem.active.is_(True)
        ))).all()
    }
    if len(catalog) != len(catalog_ids):
        raise MissingResource("Un producto o servicio no existe o está inactivo")
    invoice = Invoice(
        patient_id=payload.patient_id,
        professional_id=payload.professional_id,
        appointment_id=payload.appointment_id,
        consultation_id=payload.consultation_id,
        status="ISSUED",
        tax=payload.tax,
        discount=payload.discount,
        payment_method=payload.payment_method,
        created_by=user.id,
    )
    db.add(invoice)
    subtotal = Decimal("0.00")
    await db.flush()
    for line in payload.items:
        item = catalog[line.catalog_item_id]
        line_total = (line.quantity * item.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += line_total
        db.add(InvoiceItem(
            invoice_id=invoice.id,
            catalog_item_id=item.id,
            description=item.name,
            quantity=line.quantity,
            unit_price=item.unit_price,
            subtotal=line_total,
        ))
    invoice.subtotal = subtotal
    invoice.total = (subtotal + payload.tax - payload.discount).quantize(Decimal("0.01"))
    if invoice.total < 0:
        raise ResourceConflict("El descuento no puede superar subtotal más impuesto")
    record_audit(db, user, "billing.create", "invoice", invoice.id,
                 new_values={"subtotal": invoice.subtotal, "tax": invoice.tax,
                             "discount": invoice.discount, "total": invoice.total}, ip_address=ip)
    await db.commit()
    return await get_invoice(db, invoice.id)


async def get_invoice(db: AsyncSession, invoice_id: int):
    return await db.scalar(
        select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id)
    )


async def list_invoices(db: AsyncSession, patient_id: int | None):
    query = select(Invoice).options(selectinload(Invoice.items))
    if patient_id is not None:
        query = query.where(Invoice.patient_id == patient_id)
    return list((await db.scalars(query.order_by(Invoice.created_at.desc()).limit(200))).all())


async def mark_invoice_paid(db: AsyncSession, invoice: Invoice, payment_method: str, user: User, ip: str | None):
    if invoice.status in {"VOIDED", "PAID"}:
        raise ResourceConflict("La factura no puede cambiarse a pagada en su estado actual")
    invoice.status = "PAID"
    invoice.payment_status = "PAID"
    invoice.payment_method = payment_method
    record_audit(db, user, "billing.paid", "invoice", invoice.id,
                 {"status": "ISSUED", "payment_status": "PENDING"},
                 {"status": "PAID", "payment_status": "PAID", "payment_method": payment_method}, ip)
    await db.commit()


async def void_invoice(db: AsyncSession, invoice: Invoice, reason: str, user: User, ip: str | None):
    if invoice.status == "VOIDED":
        raise ResourceConflict("La factura ya está anulada")
    old_status = invoice.status
    invoice.status = "VOIDED"
    invoice.voided_at = datetime.now(UTC)
    invoice.voided_by = user.id
    invoice.void_reason = reason
    record_audit(db, user, "billing.void", "invoice", invoice.id,
                 {"status": old_status}, {"status": "VOIDED", "reason": reason}, ip)
    await db.commit()
