from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.schemas.auth import AuthSession, LoginRequest, TokenResponse
from app.services.auth_service import authenticate_user, get_current_user, issue_token_for_user

router = APIRouter(prefix="/auth", tags=["auth"], responses=router_default_responses("auth"))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = issue_token_for_user(db, user)
    return TokenResponse(access_token=token, expires_in_minutes=720)


@router.get("/me", response_model=AuthSession)
def me(current_user=Depends(get_current_user)) -> AuthSession:
    return AuthSession(user=current_user, issued_at=datetime.utcnow())
