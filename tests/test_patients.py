import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.clinical import AuditLog, PatientMedicalBackground
from app.models.identity import Person, User
from app.schemas.patients import BackgroundCreate, PatientCreate, PersonCreate, PersonUpdate
from app.services.patients import (
    create_background,
    create_patient,
    deactivate_background,
    deactivate_patient,
    list_backgrounds,
    update_patient,
)


class PatientServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.session_factory()
        person = Person(first_names="Admin", last_names="Test")
        self.user = User(person=person, username="test-admin", password_hash="not-used")
        self.db.add(self.user)
        await self.db.commit()
        await self.db.refresh(self.user)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_patient_history_and_deactivation_are_audited(self):
        patient = await create_patient(
            self.db,
            PatientCreate(person=PersonCreate(
                first_names="Ana",
                last_names="Lopez",
                document_type="ID",
                document_number="12345",
                birth_date=date(1990, 1, 2),
            )),
            self.user,
            "127.0.0.1",
        )
        self.assertEqual(patient.person.birth_date, date(1990, 1, 2))

        patient = await update_patient(
            self.db, patient, PersonUpdate(first_names="Ana Maria"), self.user, None
        )
        self.assertEqual(patient.person.first_names, "Ana Maria")

        background = await create_background(
            self.db,
            patient.id,
            BackgroundCreate(category="ALERGIA", description="Polen"),
            self.user,
            None,
        )
        await deactivate_background(self.db, background, self.user, None)
        self.assertEqual(await list_backgrounds(self.db, patient.id), [])

        await deactivate_patient(self.db, patient, self.user, None)
        await self.db.refresh(patient)
        self.assertFalse(patient.active)

        audit_rows = list((await self.db.scalars(select(AuditLog))).all())
        self.assertEqual(len(audit_rows), 5)
        update_audit = next(row for row in audit_rows if row.action == "patients.update")
        self.assertEqual(update_audit.old_values["first_names"], "Ana")
        self.assertEqual(update_audit.new_values["first_names"], "Ana Maria")
        self.assertEqual(
            await self.db.scalar(select(PatientMedicalBackground.active)),
            False,
        )


if __name__ == "__main__":
    unittest.main()
