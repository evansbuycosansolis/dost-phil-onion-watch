from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models import Role, User, UserRole
from app.schemas.auth import CurrentUser
from app.services.oidc_service import includes_privileged_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_user_roles(db: Session, user_id: int) -> list[str]:
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return [row[0] for row in db.execute(stmt).all()]


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_token_for_user_with_context(
    db: Session,
    user: User,
    *,
    auth_source: str,
    mfa_verified: bool,
) -> str:
    roles = get_user_roles(db, user.id)
    return create_access_token(
        str(user.id),
        extra={
            "roles": roles,
            "auth_source": auth_source,
            "mfa_verified": bool(mfa_verified),
        },
    )


def upsert_user_roles(db: Session, user: User, role_names: list[str]) -> list[str]:
    if not role_names:
        return []

    resolved_roles = list(
        db.scalars(
            select(Role).where(Role.name.in_(role_names))
        )
    )
    resolved_ids = {role.id for role in resolved_roles}
    resolved_names = sorted({role.name for role in resolved_roles})

    existing_rows = list(db.scalars(select(UserRole).where(UserRole.user_id == user.id)))
    for row in existing_rows:
        if row.role_id not in resolved_ids:
            db.delete(row)

    existing_role_ids = {row.role_id for row in existing_rows}
    for role in resolved_roles:
        if role.id not in existing_role_ids:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    db.flush()
    return resolved_names


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload.get("sub"))
        auth_source = str(payload.get("auth_source") or "local")
        mfa_verified = bool(payload.get("mfa_verified"))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise credentials_exception

    roles = get_user_roles(db, user.id)
    if settings.enforce_mfa_for_privileged_tokens and includes_privileged_role(roles) and not mfa_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA is required for privileged access",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=roles,
        municipality_id=user.municipality_id,
        auth_source=auth_source,
        mfa_verified=mfa_verified,
    )


def current_time_utc() -> datetime:
    return datetime.now(timezone.utc)
