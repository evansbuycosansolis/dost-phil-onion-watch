from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.services.dashboard_service import (
    admin_overview,
    alerts_overview,
    imports_overview,
    municipal_overview,
    prices_overview,
    provincial_overview,
    reports_overview,
    warehouses_overview,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"], responses=router_default_responses("dashboard"))

DASHBOARD_ROLES = (
    "super_admin",
    "provincial_admin",
    "municipal_encoder",
    "warehouse_operator",
    "market_analyst",
    "policy_reviewer",
    "executive_viewer",
    "auditor",
)


@router.get("/provincial/overview")
def provincial(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return provincial_overview(db, current_user)


@router.get("/municipal/{municipality_id}/overview")
def municipal(
    municipality_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    response = municipal_overview(db, municipality_id, current_user)
    if response.get("error"):
        raise HTTPException(status_code=403, detail=response["error"])
    return response


@router.get("/warehouses/overview")
def warehouses(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return warehouses_overview(db, current_user)


@router.get("/prices/overview")
def prices(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return prices_overview(db, current_user)


@router.get("/imports/overview")
def imports(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return imports_overview(db, current_user)


@router.get("/alerts/overview")
def alerts(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return alerts_overview(db, current_user)


@router.get("/reports/overview")
def reports(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*DASHBOARD_ROLES))],
):
    return reports_overview(db, current_user)


@router.get("/admin/overview")
def admin(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor"))],
):
    return admin_overview(db, current_user)
