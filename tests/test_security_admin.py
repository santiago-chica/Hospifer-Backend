import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.identity import Permission, Person, Role, User
from app.routers.auth import effective_permissions
from app.schemas.security import RoleUpdate, UserPermissionOverridesUpdate, UserUpdate
from app.services.security import SecurityConflict, update_role, update_user, update_user_overrides


class SecurityAdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.factory()
        self.read_permission = Permission(code="patients.read")
        self.update_permission = Permission(code="patients.update")
        self.role = Role(name="CLINICIAN", permissions=[self.read_permission])
        actor_person = Person(first_names="Main", last_names="Admin")
        self.actor = User(
            person=actor_person,
            username="main-admin",
            password_hash="unused",
            is_primary_admin=True,
        )
        target_person = Person(first_names="Staff", last_names="Member")
        self.target = User(
            person=target_person,
            username="staff-user",
            password_hash="unused",
            roles=[self.role],
        )
        self.db.add_all([self.actor, self.target, self.update_permission])
        await self.db.commit()
        await self.db.refresh(self.actor)
        await self.db.refresh(self.target)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_user_overrides_allow_and_deny_role_permissions(self):
        await update_user_overrides(
            self.db,
            self.target.id,
            UserPermissionOverridesUpdate(overrides=[
                {"code": "patients.read", "granted": False},
                {"code": "patients.update", "granted": True},
            ]),
            self.actor,
        )
        from app.services.security import _get_user
        target = await _get_user(self.db, self.target.id)
        permissions = effective_permissions(target)
        self.assertNotIn("patients.read", permissions)
        self.assertIn("patients.update", permissions)

    async def test_primary_admin_cannot_be_deactivated_or_lose_admin_role(self):
        with self.assertRaises(SecurityConflict):
            await update_user(self.db, self.actor.id, UserUpdate(active=False), self.actor)

        admin_role = Role(name="ADMIN", permissions=[self.read_permission, self.update_permission])
        self.db.add(admin_role)
        await self.db.commit()
        with self.assertRaises(SecurityConflict):
            await update_role(
                self.db,
                admin_role.id,
                RoleUpdate(permission_codes=["patients.read"]),
                self.actor,
            )


if __name__ == "__main__":
    unittest.main()
