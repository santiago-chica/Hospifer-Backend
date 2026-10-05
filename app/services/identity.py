from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.identity import Permission, Person, Role, User
from app.security import hash_password

PERMISSIONS = {
    "patients.read": "Consultar pacientes",
    "patients.create": "Registrar pacientes",
    "patients.update": "Actualizar pacientes",
    "patients.deactivate": "Desactivar pacientes",
    "patients.contact.read": "Consultar datos de contacto",
    "patients.history.read": "Consultar historia clínica",
    "patients.medical_history.read": "Consultar antecedentes",
    "patients.background.create": "Registrar antecedentes",
    "professionals.read": "Consultar profesionales",
    "professionals.create": "Registrar profesionales",
    "professionals.update": "Actualizar profesionales",
    "professionals.deactivate": "Desactivar profesionales",
    "appointments.read": "Consultar citas",
    "appointments.create": "Crear citas",
    "appointments.update": "Actualizar citas",
    "appointments.confirm": "Confirmar citas",
    "appointments.cancel": "Cancelar citas",
    "medical_consultations.read": "Consultar atenciones médicas",
    "medical_consultations.create": "Crear atenciones médicas",
    "medical_consultations.update": "Actualizar atenciones médicas",
    "medical_consultations.void": "Anular atenciones médicas",
    "medical_history.read": "Consultar historias clínicas",
    "medical_history.export": "Exportar historias clínicas",
    "billing.read": "Consultar facturación",
    "billing.create": "Crear facturas",
    "billing.update": "Actualizar facturas",
    "billing.void": "Anular facturas",
    "products.read": "Consultar productos y servicios",
    "products.create": "Crear productos y servicios",
    "products.update": "Actualizar productos y servicios",
    "products.deactivate": "Desactivar productos y servicios",
    "users.read": "Consultar usuarios",
    "users.create": "Crear usuarios",
    "users.update": "Actualizar usuarios",
    "users.deactivate": "Desactivar usuarios",
    "roles.read": "Consultar roles",
    "roles.create": "Crear roles",
    "roles.update": "Actualizar roles",
    "permissions.read": "Consultar permisos",
    "permissions.update": "Modificar permisos",
    "audit.read": "Consultar auditoría",
    "profile.read": "Consultar perfil propio",
    "profile.update": "Actualizar perfil propio",
    "appointments.complete": "Completar citas",
    "specialties.read": "Consultar especialidades",
    "specialties.create": "Crear especialidades",
}

ROLE_PERMISSIONS = {
    "DOCTOR": {
        "patients.read", "patients.contact.read", "patients.history.read",
        "patients.medical_history.read", "patients.background.create", "professionals.read", "appointments.read",
        "appointments.update", "appointments.confirm", "appointments.cancel",
        "appointments.complete",
        "medical_consultations.read", "medical_consultations.create",
        "medical_consultations.update", "medical_consultations.void",
        "medical_history.read", "medical_history.export", "products.read", "profile.read", "profile.update",
    },
    "RECEPCIONISTA": {
        "patients.read", "patients.create", "patients.update", "patients.contact.read",
        "professionals.read", "appointments.read", "appointments.create",
        "appointments.update", "appointments.confirm", "appointments.cancel",
        "profile.read", "profile.update",
    },
    "FACTURACION": {
        "patients.read", "appointments.read", "billing.read", "billing.create",
        "billing.update", "billing.void", "products.read", "profile.read", "profile.update",
    },
    "USUARIO": {"profile.read", "profile.update"},
}


async def seed_initial_data() -> None:
    async with AsyncSessionLocal() as session, session.begin():
        permissions = {
            permission.code: permission
            for permission in (await session.scalars(select(Permission))).all()
        }
        for code, description in PERMISSIONS.items():
            if code not in permissions:
                permission = Permission(code=code, description=description)
                session.add(permission)
                permissions[code] = permission

        roles = {
            role.name: role
            for role in (await session.scalars(select(Role).options(selectinload(Role.permissions)))).all()
        }
        for name in ("ADMIN", *ROLE_PERMISSIONS):
            if name not in roles:
                role = Role(name=name, description=f"Rol {name.lower()}")
                session.add(role)
                roles[name] = role
                role.permissions = [
                    permissions[code]
                    for code in (PERMISSIONS if name == "ADMIN" else ROLE_PERMISSIONS[name])
                ]
        roles["ADMIN"].permissions = list(permissions.values())

        primary_admin = await session.scalar(
            select(User)
            .options(selectinload(User.roles))
            .where(User.is_primary_admin.is_(True))
            .limit(1)
        )
        if primary_admin is None:
            primary_admin = await session.scalar(
                select(User)
                .options(selectinload(User.roles))
                .where(User.username == settings.initial_admin_username)
            )
        if primary_admin is None:
            initial_password = settings.initial_admin_password
            if settings.environment == "development":
                initial_password = initial_password or "admin"
            if not initial_password:
                raise RuntimeError(
                    "Configure INITIAL_ADMIN_PASSWORD before creating the production administrator."
                )
            person = Person(first_names="Administrador", last_names="Principal")
            primary_admin = User(
                person=person,
                username=settings.initial_admin_username,
                password_hash=hash_password(initial_password),
                must_change_password=True,
                is_primary_admin=True,
                roles=[roles["ADMIN"]],
            )
            session.add(primary_admin)
        primary_admin.is_primary_admin = True
        primary_admin.active = True
        if primary_admin not in session.new and roles["ADMIN"] not in primary_admin.roles:
            primary_admin.roles.append(roles["ADMIN"])