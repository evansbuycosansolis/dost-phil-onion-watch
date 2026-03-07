import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.security import hash_password
from app.models import User
from app.schemas.auth import AuthSession, LoginRequest, OIDCLoginRequest, TokenResponse
from app.services.audit_service import emit_audit_event
from app.services.auth_service import (
    authenticate_user,
    get_current_user,
    get_user_roles,
    issue_token_for_user_with_context,
    upsert_user_roles,
)
from app.services.oidc_service import (
    OIDCValidationError,
    external_roles_from_claims,
    identity_from_claims,
    includes_privileged_role,
    mapped_local_roles,
    mfa_verified_from_claims,
    verify_oidc_id_token,
)

router = APIRouter(prefix="/auth", tags=["auth"], responses=router_default_responses("auth"))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    roles = get_user_roles(db, user.id)
    if settings.enforce_oidc_for_privileged_roles and includes_privileged_role(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OIDC login is required for privileged accounts",
        )

    token = issue_token_for_user_with_context(
        db,
        user,
        auth_source="local",
        mfa_verified=False,
    )

    emit_audit_event(
        db,
        actor_user_id=user.id,
        action_type="auth.login.local",
        entity_type="user",
        entity_id=str(user.id),
        after_payload={"email": user.email, "roles": roles},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        auth_source="local",
        mfa_verified=False,
    )


@router.post("/oidc/login", response_model=TokenResponse)
def oidc_login(payload: OIDCLoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    try:
        claims = verify_oidc_id_token(payload.id_token)
    except OIDCValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    external_roles = external_roles_from_claims(claims)
    local_roles = mapped_local_roles(external_roles)
    if not local_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No mapped local roles from OIDC claims")

    mfa_verified = mfa_verified_from_claims(claims)
    if includes_privileged_role(local_roles) and not mfa_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is required for privileged OIDC roles")

    subject, email, full_name = identity_from_claims(claims)
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC subject claim is required")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OIDC email claim is required")

    user = db.scalar(select(User).where(User.oidc_subject == subject))
    if not user:
        user = db.scalar(select(User).where(User.email == email))

    if not user:
        if not settings.oidc_auto_provision_users:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OIDC user is not provisioned")
        user = User(
            email=email,
            full_name=full_name or email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            auth_provider="oidc",
            oidc_subject=subject,
            is_active=True,
        )
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    user.auth_provider = "oidc"
    user.oidc_subject = subject
    if full_name:
        user.full_name = full_name

    if settings.oidc_sync_roles_on_login:
        assigned_roles = upsert_user_roles(db, user, local_roles)
    else:
        assigned_roles = get_user_roles(db, user.id)

    if not assigned_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No valid local roles assigned for OIDC user")

    if includes_privileged_role(assigned_roles) and not mfa_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA is required for privileged OIDC roles")

    if mfa_verified:
        user.last_mfa_verified_at = datetime.utcnow()

    token = issue_token_for_user_with_context(
        db,
        user,
        auth_source="oidc",
        mfa_verified=mfa_verified,
    )

    emit_audit_event(
        db,
        actor_user_id=user.id,
        action_type="auth.login.oidc",
        entity_type="user",
        entity_id=str(user.id),
        after_payload={
            "email": user.email,
            "subject": subject,
            "external_roles": external_roles,
            "assigned_roles": assigned_roles,
            "mfa_verified": mfa_verified,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        auth_source="oidc",
        mfa_verified=mfa_verified,
    )


@router.get("/me", response_model=AuthSession)
def me(current_user=Depends(get_current_user)) -> AuthSession:
    return AuthSession(user=current_user, issued_at=datetime.utcnow())
