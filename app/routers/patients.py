from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.clinical import Patient, PatientMedicalBackground
from app.models.identity import User
from app.routers.auth import get_current_user, require_permissions
from app.schemas.patients import (
    BackgroundCreate,
    BackgroundResponse,
    PatientContactResponse,
    PatientCreate,
    PatientResponse,
    PersonUpdate,
)
from app.services import patients as patient_service
from app.services import documents as document_service
from app.services.operations import MissingResource, ResourceConflict

router = APIRouter(prefix="/patients", tags=["Pacientes"])


@router.get("/{patient_id}/history.pdf")
async def export_patient_history(
    patient_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("medical_history.export"))],
    consultation_ids: list[int] | None = Query(default=None),
):
    try:
        content = await document_service.render_patient_history(
            db, user, patient_id, consultation_ids
        )
    except MissingResource as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ResourceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=patient-{patient_id}-history.pdf"},
    )


async def _required_patient(db: AsyncSession, patient_id: int) -> Patient:
    patient = await patient_service.get_patient(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paciente no encontrado")
    return patient


@router.get("/", response_model=list[PatientResponse])
async def list_patients(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.read"))],
    search: str | None = Query(default=None, max_length=120),
    active: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return await patient_service.list_patients(db, search, active, offset, limit)


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.create"))],
):
    try:
        return await patient_service.create_patient(db, payload, user, request.client.host if request.client else None)
    except IntegrityError as error:
        await db.rollback()
        if "uq_person_document" in str(error) or "UNIQUE constraint failed" in str(error):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El documento ya está registrado") from error
        raise


@router.get("/{patient_id}", response_model=PatientResponse)
async def read_patient(
    patient_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.read"))],
):
    return await _required_patient(db, patient_id)


@router.get("/{patient_id}/contact", response_model=PatientContactResponse)
async def read_patient_contact(
    patient_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.contact.read"))],
):
    patient = await _required_patient(db, patient_id)
    return patient.person


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    payload: PersonUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.update"))],
):
    patient = await _required_patient(db, patient_id)
    return await patient_service.update_patient(
        db, patient, payload, user, request.client.host if request.client else None
    )


@router.post("/{patient_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_patient(
    patient_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.deactivate"))],
):
    patient = await _required_patient(db, patient_id)
    await patient_service.deactivate_patient(
        db, patient, user, request.client.host if request.client else None
    )


@router.get("/{patient_id}/backgrounds", response_model=list[BackgroundResponse])
async def list_backgrounds(
    patient_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.medical_history.read"))],
):
    await _required_patient(db, patient_id)
    return await patient_service.list_backgrounds(db, patient_id)


@router.post(
    "/{patient_id}/backgrounds",
    response_model=BackgroundResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_background(
    patient_id: int,
    payload: BackgroundCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.background.create"))],
):
    patient = await _required_patient(db, patient_id)
    if not patient.active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No se puede actualizar un paciente inactivo")
    return await patient_service.create_background(
        db, patient_id, payload, user, request.client.host if request.client else None
    )


@router.post("/backgrounds/{background_id}/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_background(
    background_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    user: Annotated[User, Depends(require_permissions("patients.update"))],
):
    background = await db.scalar(
        select(PatientMedicalBackground).where(PatientMedicalBackground.id == background_id)
    )
    if background is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Antecedente no encontrado")
    await patient_service.deactivate_background(
        db, background, user, request.client.host if request.client else None
    )