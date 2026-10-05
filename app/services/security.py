from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clinical import AuditLog
from app.models.identity import (
    Permission,
    Person,
    Role,
    User,
    UserPermissionOverride,
)
from app.schemas.security import (
    RoleCreate,
    RoleUpdate,
    UserCreate,
    UserPermissionOverridesUpdate,
    UserUpdate,
)
from app.security import hash_password
from app.services.identity import PERMISSIONS


class SecurityResourceMissing(Exception):
    pass


class SecurityConflict(Exception):
    pass


def _audit(db: AsyncSession, actor: User, action: str, entity_type: str, entity_id: int,
           old_values: dict | None = None, new_values: dict | None = None):
    db.add(AuditLog(
        user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
    ))


async def list_users(db: AsyncSession) -> list[User]:
    query = select(User).options(
        selectinload(User.person),
        selectinload(User.roles).selectinload(Role.permissions),
        selectinload(User.permission_overrides).selectinload(UserPermissionOverride.permission),
    ).order_by(User.username)
    return list((await db.scalars(query)).all())


async def create_user(db: AsyncSession, payload: UserCreate, actor: User) -> User:
    roles = list((await db.scalars(
        select(Role).where(Role.id.in_(payload.role_ids), Role.active.is_(True))
    )).all()) if payload.role_ids else []
    if len(roles) != len(set(payload.role_ids)):
        raise SecurityResourceMissing("Uno o más roles no existen o están inactivos")
    user = User(
        person=Person(**payload.person.model_dump()),
        username=payload.username,
        password_hash=hash_password(payload.password),
        must_change_password=True,
        roles=roles,
    )
    db.add(user)
    await db.flush()
    _audit(db, actor, "users.create", "user", user.id,
           new_values={"username": user.username, "role_ids": payload.role_ids})
    await db.commit()
    return await _get_user(db, user.id)


async def _get_user(db: AsyncSession, user_id: int) -> User | None:
    query = select(User).options(
        selectinload(User.person),
        selectinload(User.roles).selectinload(Role.permissions),
        selectinload(User.permission_overrides).selectinload(UserPermissionOverride.permission),
    ).where(User.id == user_id).execution_options(populate_existing=True)
    return await db.scalar(query)


async def update_user(db: AsyncSession, user_id: int, payload: UserUpdate, actor: User) -> User:
    user = await _get_user(db, user_id)
    if user is None:
        raise SecurityResourceMissing("Usuario no encontrado")
    changes = payload.model_dump(exclude_unset=True)
    old_values: dict = {}
    if "active" in changes:
        if user.is_primary_admin and changes["active"] is False:
            raise SecurityConflict("No se puede desactivar al administrador principal")
        old_values["active"] = user.active
        user.active = changes["active"]
    if "role_ids" in changes:
        role_ids = changes["role_ids"] or []
        roles = list((await db.scalars(
            select(Role).where(Role.id.in_(role_ids), Role.active.is_(True))
        )).all()) if role_ids else []
        if len(roles) != len(set(role_ids)):
            raise SecurityResourceMissing("Uno o más roles no existen o están inactivos")
        if user.is_primary_admin and not any(role.name == "ADMIN" for role in roles):
            raise SecurityConflict("El administrador principal debe conservar el rol ADMIN")
        old_values["roles"] = [role.name for role in user.roles]
        user.roles = roles
    _audit(db, actor, "users.update", "user", user.id, old_values, changes)
    await db.commit()
    return await _get_user(db, user.id)


async def list_roles(db: AsyncSession) -> list[Role]:
    query = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    return list((await db.scalars(query)).all())


async def create_role(db: AsyncSession, payload: RoleCreate, actor: User) -> Role:
    permissions = list((await db.scalars(
        select(Permission).where(Permission.code.in_(payload.permission_codes))
    )).all()) if payload.permission_codes else []
    if len(permissions) != len(set(payload.permission_codes)):
        raise SecurityResourceMissing("Uno o más permisos no existen")
    role = Role(name=payload.name.upper(), description=payload.description, permissions=permissions)
    db.add(role)
    await db.flush()
    _audit(db, actor, "roles.create", "role", role.id,
           new_values={"name": role.name, "permission_codes": payload.permission_codes})
    await db.commit()
    await db.refresh(role)
    return role


async def update_role(db: AsyncSession, role_id: int, payload: RoleUpdate, actor: User) -> Role:
    role = await db.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    if role is None:
        raise SecurityResourceMissing("Rol no encontrado")
    changes = payload.model_dump(exclude_unset=True)
    if role.name == "ADMIN" and (
        changes.get("active") is False
        or ("permission_codes" in changes and set(changes["permission_codes"] or []) != set(PERMISSIONS))
    ):
        raise SecurityConflict("El rol ADMIN debe permanecer activo y conservar todos los permisos")
    old_values = {"name": role.name, "active": role.active,
                  "permission_codes": [item.code for item in role.permissions]}
    if "permission_codes" in changes:
        codes = set(changes["permission_codes"] or [])
        permissions = list((await db.scalars(select(Permission).where(Permission.code.in_(codes)))).all())
        if len(permissions) != len(codes):
            raise SecurityResourceMissing("Uno o más permisos no existen")
        role.permissions = permissions
    for field in ("name", "description", "active"):
        if field in changes and changes[field] is not None:
            setattr(role, field, changes[field].upper() if field == "name" else changes[field])
    _audit(db, actor, "roles.update", "role", role.id, old_values, changes)
    await db.commit()
    return await db.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role.id)
    )


async def list_permissions(db: AsyncSession) -> list[Permission]:
    return list((await db.scalars(select(Permission).order_by(Permission.code))).all())


async def list_user_overrides(db: AsyncSession, user_id: int) -> list[UserPermissionOverride]:
    user = await _get_user(db, user_id)
    if user is None:
        raise SecurityResourceMissing("Usuario no encontrado")
    return user.permission_overrides


async def update_user_overrides(
    db: AsyncSession, user_id: int, payload: UserPermissionOverridesUpdate, actor: User
) -> User:
    user = await _get_user(db, user_id)
    if user is None:
        raise SecurityResourceMissing("Usuario no encontrado")
    if user.is_primary_admin:
        raise SecurityConflict("No se pueden limitar permisos del administrador principal")
    requested = {item.code: item.granted for item in payload.overrides}
    permissions = list((await db.scalars(
        select(Permission).where(Permission.code.in_(requested))
    )).all()) if requested else []
    if len(permissions) != len(requested):
        raise SecurityResourceMissing("Uno o más permisos no existen")
    existing = {item.permission.code: item for item in user.permission_overrides}
    for code, granted in requested.items():
        if code in existing:
            existing[code].granted = granted
        else:
            permission = next(item for item in permissions if item.code == code)
            db.add(UserPermissionOverride(user_id=user.id, permission_id=permission.id, granted=granted))
    for code, override in existing.items():
        if code not in requested:
            await db.delete(override)
    _audit(db, actor, "users.permissions.update", "user", user.id,
           old_values={code: item.granted for code, item in existing.items()}, new_values=requested)
    await db.commit()
    return await _get_user(db, user.id)
