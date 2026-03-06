from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.schemas.auth import CurrentUser
from app.services.auth_service import get_current_user


RoleGuard = Callable[[CurrentUser], CurrentUser]


def require_role(*allowed_roles: str):
    def dependency(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if not set(current_user.roles).intersection(set(allowed_roles)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return current_user

    return dependency
