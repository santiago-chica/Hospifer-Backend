from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi.encoders import jsonable_encoder

from app.models.clinical import AuditLog, Patient, PatientMedicalBackground
from app.models.identity import Person, User
from app.schemas.patients import BackgroundCreate, PatientCreate, PersonUpdate


def _audit(
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
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
    ))


async def list_patients(
    db: AsyncSession, search: str | None, active: bool | None, offset: int, limit: int
) -> list[Patient]:
    query = select(Patient).options(selectinload(Patient.person)).order_by(Patient.id.desc())
    if active is not None:
        query = query.where(Patient.active.is_(active))
    if search:
        term = f"%{search.strip()}%"
        query = query.join(Patient.person).where(
            or_(Person.first_names.ilike(term), Person.last_names.ilike(term), Person.document_number.ilike(term))
        )
    return list((await db.scalars(query.offset(offset).limit(limit))).all())


async def get_patient(db: AsyncSession, patient_id: int) -> Patient | None:
    return await db.scalar(
        select(Patient).options(selectinload(Patient.person)).where(Patient.id == patient_id)
    )


async def create_patient(
    db: AsyncSession, payload: PatientCreate, user: User, ip_address: str | None
) -> Patient:
    person_data = payload.person.model_dump()
    person = Person(**person_data)
    patient = Patient(person=person)
    db.add(patient)
    await db.flush()
    _audit(
        db,
        user,
        "patients.create",
        "patient",
        patient.id,
        new_values=jsonable_encoder(person_data),
        ip_address=ip_address,
    )
    await db.commit()
    return await get_patient(db, patient.id)  # type: ignore[return-value]


async def update_patient(
    db: AsyncSession,
    patient: Patient,
    payload: PersonUpdate,
    user: User,
    ip_address: str | None,
) -> Patient:
    changes = payload.model_dump(exclude_unset=True)
    old_values = jsonable_encoder({key: getattr(patient.person, key) for key in changes})
    for key, value in changes.items():
        setattr(patient.person, key, value)
    _audit(
        db,
        user,
        "patients.update",
        "patient",
        patient.id,
        old_values,
        jsonable_encoder(changes),
        ip_address,
    )
    await db.commit()
    return await get_patient(db, patient.id)  # type: ignore[return-value]


async def deactivate_patient(
    db: AsyncSession, patient: Patient, user: User, ip_address: str | None
) -> None:
    patient.active = False
    _audit(db, user, "patients.deactivate", "patient", patient.id, {"active": True}, {"active": False}, ip_address)
    await db.commit()


async def list_backgrounds(db: AsyncSession, patient_id: int) -> list[PatientMedicalBackground]:
    query = (
        select(PatientMedicalBackground)
        .where(PatientMedicalBackground.patient_id == patient_id, PatientMedicalBackground.active.is_(True))
        .order_by(PatientMedicalBackground.occurred_on.desc(), PatientMedicalBackground.id.desc())
    )
    return list((await db.scalars(query)).all())


async def create_background(
    db: AsyncSession,
    patient_id: int,
    payload: BackgroundCreate,
    user: User,
    ip_address: str | None,
) -> PatientMedicalBackground:
    background = PatientMedicalBackground(patient_id=patient_id, **payload.model_dump())
    db.add(background)
    await db.flush()
    _audit(
        db,
        user,
        "patients.background.create",
        "patient_medical_background",
        background.id,
        new_values=payload.model_dump(mode="json"),
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(background)
    return background


async def deactivate_background(
    db: AsyncSession,
    background: PatientMedicalBackground,
    user: User,
    ip_address: str | None,
) -> None:
    background.active = False
    _audit(
        db,
        user,
        "patients.background.deactivate",
        "patient_medical_background",
        background.id,
        {"active": True},
        {"active": False},
        ip_address,
    )
    await db.commit()