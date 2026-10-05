from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_db
from app.models.identity import Role, User, UserPermissionOverride
from app.models.clinical import AuditLog
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    TokenResponse,
    UserResponse,
)
from app.services.identity import PERMISSIONS
from app.security import create_access_token, decode_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Autenticación"])
bearer_scheme = HTTPBearer(auto_error=False)


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        active=user.active,
        must_change_password=user.must_change_password,
        is_primary_admin=user.is_primary_admin,
        profile_photo=user.profile_photo,
        roles=[role.name for role in user.roles],
        permissions=sorted(effective_permissions(user)),
        person=user.person,
    )


def effective_permissions(user: User) -> set[str]:
    if user.is_primary_admin:
        return set(PERMISSIONS)
    granted = {permission.code for role in user.roles if role.active for permission in role.permissions}
    for override in user.permission_overrides:
        if override.granted:
            granted.add(override.permission.code)
        else:
            granted.discard(override.permission.code)
    return granted


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> User:
    user_id = decode_access_token(credentials.credentials) if credentials else None
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    user = await db.scalar(
        select(User)
        .options(
            selectinload(User.person),
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.permission_overrides).selectinload(UserPermissionOverride.permission),
        )
        .where(User.id == user_id, User.active.is_(True))
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    return user


def require_permissions(*required: str):
    async def permission_check(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.must_change_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Debes cambiar tu contraseña antes de continuar",
            )
        if not set(required).issubset(effective_permissions(user)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")
        return user

    return permission_check


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_db)],
):
    user = await db.scalar(
        select(User).where(User.username == payload.username, User.active.is_(True))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")
    user_id = user.id
    user.last_login = datetime.now(UTC)
    db.add(AuditLog(
        user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(user_id),
        must_change_password=user.must_change_password,
    )


@router.get("/me", response_model=UserResponse)
async def read_current_user(user: Annotated[User, Depends(get_current_user)]):
    return user_response(user)


@router.post("/change-password", response_model=UserResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_db)],
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es válida")
    if len(payload.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La contraseña excede el máximo admitido")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.add(AuditLog(
        user_id=user.id,
        action="auth.password.change",
        entity_type="user",
        entity_id=user.id,
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()
    await db.refresh(user)
    return user_response(user)


@router.patch("/me", response_model=UserResponse)
async def update_current_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: Annotated[User, Depends(require_permissions("profile.update"))],
    db: Annotated[AsyncSession, Depends(get_async_db)],
):
    changes = payload.model_dump(exclude_unset=True)
    old_values = {}
    new_values = {}
    for field, value in changes.items():
        target = user if field == "profile_photo" else user.person
        old_values[field] = getattr(target, field)
        setattr(target, field, value)
        new_values[field] = value
    db.add(AuditLog(
        user_id=user.id,
        action="profile.update",
        entity_type="user",
        entity_id=user.id,
        old_values=old_values,
        new_values=new_values,
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()
    return user_response(user)