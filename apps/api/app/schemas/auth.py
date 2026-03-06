from datetime import datetime
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class CurrentUser(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[str]
    municipality_id: int | None = None


class UserSummary(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[str]
    is_active: bool


class AuthSession(BaseModel):
    user: CurrentUser
    issued_at: datetime
