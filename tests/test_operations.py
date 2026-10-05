import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.clinical import AuditLog, Patient
from app.models.identity import Person, User
from app.models.operations import (
    Appointment,
    CatalogItem,
    InvoiceItem,
    Medication,
    Professional,
    Specialty,
)
from app.schemas.operations import (
    AppointmentCreate,
    ConsultationCreate,
    InvoiceCreate,
    InvoiceLineCreate,
    PrescriptionCreate,
)
from app.services.operations import (
    ResourceConflict,
    create_appointment,
    create_consultation,
    create_invoice,
    transition_appointment,
    void_invoice,
)
from app.services.documents import render_consultation_pdf, render_patient_history
from app.services.operations import list_consultations


class OperationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.session_factory()

        user_person = Person(first_names="Admin", last_names="Test")
        self.user = User(person=user_person, username="operations-admin", password_hash="unused")
        patient_person = Person(first_names="Patient", last_names="Test")
        self.patient = Patient(person=patient_person)
        professional_person = Person(first_names="Doctor", last_names="Test")
        specialty = Specialty(name="General")
        self.professional = Professional(
            person=professional_person,
            profession="Physician",
            specialties=[specialty],
        )
        self.medication = Medication(name="Example medicine")
        self.catalog_item = CatalogItem(item_type="SERVICE", name="Consultation", unit_price=Decimal("25.00"))
        self.db.add_all([self.user, self.patient, self.professional, self.medication, self.catalog_item])
        await self.db.commit()
        await self.db.refresh(self.user)
        await self.db.refresh(self.patient)
        await self.db.refresh(self.professional)
        await self.db.refresh(self.medication)
        await self.db.refresh(self.catalog_item)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_appointment_overlap_and_multiple_consultations(self):
        start = datetime.now(UTC) + timedelta(days=5)
        appointment = await create_appointment(
            self.db,
            AppointmentCreate(
                patient_id=self.patient.id,
                professional_id=self.professional.id,
                start_at=start,
                end_at=start + timedelta(hours=1),
            ),
            self.user,
            None,
        )
        with self.assertRaises(ResourceConflict):
            await create_appointment(
                self.db,
                AppointmentCreate(
                    patient_id=self.patient.id,
                    professional_id=self.professional.id,
                    start_at=start + timedelta(minutes=30),
                    end_at=start + timedelta(hours=2),
                ),
                self.user,
                None,
            )

        appointment = await transition_appointment(self.db, appointment, "confirm", self.user, None)
        for diagnosis in ("First assessment", "Follow-up assessment"):
            await create_consultation(
                self.db,
                ConsultationCreate(
                    appointment_id=appointment.id,
                    professional_id=self.professional.id,
                    diagnosis=diagnosis,
                    weight=Decimal("70.5"),
                    medications=[PrescriptionCreate(
                        medication_id=self.medication.id,
                        dose="1 tablet",
                        frequency="Twice daily",
                        duration="5 days",
                        route="oral",
                    )],
                ),
                self.user,
                None,
            )
        stored = list((await self.db.scalars(select(Appointment))).all())
        self.assertEqual(stored[0].status, "CONFIRMED")
        consultations = await list_consultations(self.db, self.patient.id)
        patient_pdf = await render_patient_history(self.db, self.user, self.patient.id)
        consultation_pdf, exported_patient_id = await render_consultation_pdf(
            self.db, self.user, consultations[0].id
        )
        self.assertTrue(patient_pdf.startswith(b"%PDF"))
        self.assertTrue(consultation_pdf.startswith(b"%PDF"))
        self.assertEqual(exported_patient_id, self.patient.id)

    async def test_invoice_keeps_price_snapshot_and_audits_void(self):
        invoice = await create_invoice(
            self.db,
            InvoiceCreate(
                patient_id=self.patient.id,
                tax=Decimal("2.50"),
                discount=Decimal("1.00"),
                items=[InvoiceLineCreate(catalog_item_id=self.catalog_item.id, quantity=Decimal("2"))],
            ),
            self.user,
            None,
        )
        self.assertEqual(invoice.total, Decimal("51.50"))
        self.catalog_item.unit_price = Decimal("80.00")
        await self.db.commit()
        stored_line = await self.db.scalar(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
        self.assertEqual(stored_line.unit_price, Decimal("25.00"))
        self.assertEqual(stored_line.subtotal, Decimal("50.00"))

        await void_invoice(self.db, invoice, "Correction", self.user, None)
        audit = await self.db.scalar(select(AuditLog).where(AuditLog.action == "billing.void"))
        self.assertEqual(audit.old_values["status"], "ISSUED")
        self.assertEqual(audit.new_values["status"], "VOIDED")


if __name__ == "__main__":
    unittest.main()
