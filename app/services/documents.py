from io import BytesIO
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinical import AuditLog, Patient
from app.models.identity import User
from app.models.operations import (
    Appointment,
    ConsultationMedication,
    MedicalConsultation,
    Professional,
)
from app.services.operations import MissingResource, ResourceConflict


def _text(value) -> str:
    return escape(str(value)) if value not in (None, "") else "No registrado"


def _build_pdf(title: str, patient: Patient, consultations: list[MedicalConsultation]) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("HOSPIFER · GESTIÓN CLÍNICA", styles["Heading2"]),
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 5 * mm),
        Paragraph("Datos del paciente", styles["Heading2"]),
    ]
    person = patient.person
    patient_rows = [
        ["Nombre", _text(f"{person.first_names} {person.last_names}")],
        ["Documento", _text(f"{person.document_type or ''} {person.document_number or ''}".strip())],
        ["Nacimiento", _text(person.birth_date)],
        ["Teléfono", _text(person.phone)],
        ["Correo", _text(person.email)],
        ["Dirección", _text(person.address)],
    ]
    story.append(Table(patient_rows, colWidths=[38 * mm, 130 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2ed")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#263c32")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dce4dc")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])))
    story.append(Spacer(1, 7 * mm))

    for index, consultation in enumerate(consultations, start=1):
        professional = consultation.professional
        patient_appointment = consultation.appointment
        created = consultation.created_at.strftime("%Y-%m-%d %H:%M") if consultation.created_at else "No registrada"
        story.extend([
            Paragraph(f"Consulta {index} · {created}", styles["Heading2"]),
            Paragraph(
                f"Profesional: {_text(professional.person.first_names + ' ' + professional.person.last_names)} · "
                f"{_text(professional.profession)} · "
                f"{_text(', '.join(item.name for item in professional.specialties))}",
                styles["BodyText"],
            ),
        ])
        if consultation.voided_at:
            story.append(Paragraph(
                f"ANULADA ({consultation.voided_at:%Y-%m-%d %H:%M}): {_text(consultation.void_reason)}",
                styles["BodyText"],
            ))
        fields = [
            ("Motivo", consultation.reason),
            ("Signos vitales", "; ".join(
                f"{label}: {value}" for label, value in [
                    ("Peso", consultation.weight), ("Talla", consultation.height),
                    ("Temperatura", consultation.temperature), ("Frecuencia cardiaca", consultation.heart_rate),
                    ("Frecuencia respiratoria", consultation.respiratory_rate),
                    ("Saturación O2", consultation.oxygen_saturation),
                    ("Presión sistólica", consultation.blood_pressure_systolic),
                    ("Presión diastólica", consultation.blood_pressure_diastolic),
                ] if value is not None
            ) or "No registrados"),
            ("Diagnóstico", consultation.diagnosis),
            ("Observaciones", consultation.observations),
            ("Tratamiento", consultation.treatment),
            ("Notas", consultation.notes),
        ]
        for label, value in fields:
            story.append(Paragraph(f"<b>{label}:</b> {_text(value)}", styles["BodyText"]))
        if consultation.medications:
            story.append(Paragraph("Medicamentos", styles["Heading3"]))
            medication_rows = [["Medicamento", "Dosis", "Frecuencia", "Duración", "Vía"]]
            medication_rows.extend([
                [
                    _text(item.medication.name), _text(item.dose), _text(item.frequency),
                    _text(item.duration), _text(item.route),
                ]
                for item in consultation.medications
            ])
            story.append(Table(medication_rows, repeatRows=1, style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17463b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dce4dc")),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("PADDING", (0, 0), (-1, -1), 5),
            ])))
        if index < len(consultations):
            story.append(Spacer(1, 6 * mm))
    document.build(story)
    return output.getvalue()


async def render_patient_history(
    db: AsyncSession,
    user: User,
    patient_id: int,
    consultation_ids: list[int] | None = None,
) -> bytes:
    patient = await db.scalar(
        select(Patient).options(selectinload(Patient.person)).where(Patient.id == patient_id)
    )
    if patient is None:
        raise MissingResource("Paciente no encontrado")
    query = select(MedicalConsultation).options(
        selectinload(MedicalConsultation.appointment),
        selectinload(MedicalConsultation.professional).options(
            selectinload(Professional.person), selectinload(Professional.specialties)
        ),
        selectinload(MedicalConsultation.medications).selectinload(ConsultationMedication.medication),
    ).join(Appointment).where(Appointment.patient_id == patient_id)
    if consultation_ids:
        query = query.where(MedicalConsultation.id.in_(consultation_ids))
    consultations = list((await db.scalars(query.order_by(MedicalConsultation.created_at))).all())
    if consultation_ids and len(consultations) != len(set(consultation_ids)):
        raise ResourceConflict("Una consulta seleccionada no pertenece al paciente indicado")
    db.add(AuditLog(
        user_id=user.id,
        action="medical_history.export",
        entity_type="patient",
        entity_id=patient.id,
        new_values={"consultation_ids": consultation_ids},
    ))
    await db.commit()
    title = "Historia clínica" if consultation_ids is None else "Historia clínica · consultas seleccionadas"
    return _build_pdf(title, patient, consultations)


async def render_consultation_pdf(db: AsyncSession, user: User, consultation_id: int) -> tuple[bytes, int]:
    consultation = await db.scalar(
        select(MedicalConsultation).options(
            selectinload(MedicalConsultation.appointment).options(
                selectinload(Appointment.patient).options(
                    selectinload(Patient.person)
                )
            ),
            selectinload(MedicalConsultation.professional).options(
                selectinload(Professional.person), selectinload(Professional.specialties)
            ),
            selectinload(MedicalConsultation.medications).selectinload(ConsultationMedication.medication),
        ).where(MedicalConsultation.id == consultation_id)
    )
    if consultation is None:
        raise MissingResource("Consulta no encontrada")
    patient = consultation.appointment.patient
    db.add(AuditLog(
        user_id=user.id,
        action="medical_consultation.export",
        entity_type="medical_consultation",
        entity_id=consultation.id,
    ))
    await db.commit()
    content = _build_pdf("Consulta médica", patient, [consultation])
    return content, patient.id
