from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.identity import Role, User
from app.routers.auth import effective_permissions, require_permissions
from app.schemas.security import (
    PermissionResponse,
    RoleCreate,
    RoleUpdate,
    PermissionOverrideInput,
    UserAdminResponse,
    UserCreate,
    UserPermissionOverridesUpdate,
    UserUpdate,
)
from app.services import security as service

router = APIRouter(prefix="/security", tags=["Seguridad"])


def _response(user: User) -> UserAdminResponse:
    return UserAdminResponse(
        id=user.id,
        username=user.username,
        active=user.active,
        must_change_password=user.must_change_password,
        is_primary_admin=user.is_primary_admin,
        roles=[role.name for role in user.roles],
        permissions=sorted(effective_permissions(user)),
        first_names=user.person.first_names,
        last_names=user.person.last_names,
    )


def _translate(error: Exception):
    if isinstance(error, service.SecurityResourceMissing):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, service.SecurityConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise error


@router.get("/users", response_model=list[UserAdminResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("users.read"))],
):
    return [_response(user) for user in await service.list_users(db)]


@router.post("/users", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("users.create"))],
):
    try:
        return _response(await service.create_user(db, payload, actor))
    except service.SecurityResourceMissing as error:
        _translate(error)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="El usuario o documento ya existe") from error


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("users.update"))],
):
    try:
        return _response(await service.update_user(db, user_id, payload, actor))
    except (service.SecurityResourceMissing, service.SecurityConflict) as error:
        _translate(error)


@router.get("/roles")
async def list_roles(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("roles.read"))],
):
    roles = await service.list_roles(db)
    return [
        {"id": role.id, "name": role.name, "description": role.description,
         "active": role.active, "permission_codes": sorted(permission.code for permission in role.permissions)}
        for role in roles
    ]


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("roles.create"))],
):
    try:
        role = await service.create_role(db, payload, actor)
        return {"id": role.id, "name": role.name, "description": role.description,
                "active": role.active, "permission_codes": sorted(p.code for p in role.permissions)}
    except service.SecurityResourceMissing as error:
        _translate(error)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="El nombre del rol ya existe") from error


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("roles.update"))],
):
    try:
        role = await service.update_role(db, role_id, payload, actor)
        return {"id": role.id, "name": role.name, "description": role.description,
                "active": role.active, "permission_codes": sorted(p.code for p in role.permissions)}
    except (service.SecurityResourceMissing, service.SecurityConflict) as error:
        _translate(error)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="El nombre del rol ya existe") from error


@router.get("/permissions", response_model=list[PermissionResponse])
async def list_permissions(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("permissions.read"))],
):
    return await service.list_permissions(db)


@router.get("/users/{user_id}/permissions", response_model=list[PermissionOverrideInput])
async def list_user_overrides(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("permissions.read"))],
):
    try:
        overrides = await service.list_user_overrides(db, user_id)
        return [{"code": item.permission.code, "granted": item.granted} for item in overrides]
    except service.SecurityResourceMissing as error:
        _translate(error)


@router.put("/users/{user_id}/permissions", response_model=UserAdminResponse)
async def set_user_overrides(
    user_id: int,
    payload: UserPermissionOverridesUpdate,
    db: Annotated[AsyncSession, Depends(get_async_db)],
    actor: Annotated[User, Depends(require_permissions("permissions.update"))],
):
    try:
        return _response(await service.update_user_overrides(db, user_id, payload, actor))
    except (service.SecurityResourceMissing, service.SecurityConflict) as error:
        _translate(error)
