from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import ColdStorageFacility, ColdStorageStockReport
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/cold-storage", tags=["cold-storage"], responses=router_default_responses("cold-storage"))


@router.get("/")
def list_cold_storage(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "executive_viewer", "auditor"))],
):
    stmt = select(ColdStorageFacility).order_by(ColdStorageFacility.name)
    if "warehouse_operator" in current_user.roles and current_user.municipality_id:
        stmt = stmt.where(ColdStorageFacility.municipality_id == current_user.municipality_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "municipality_id": r.municipality_id,
            "warehouse_id": r.warehouse_id,
            "location": r.location,
            "capacity_tons": r.capacity_tons,
        }
        for r in rows
    ]


@router.get("/stock-reports")
def list_cold_storage_reports(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "executive_viewer", "auditor"))],
):
    rows = db.scalars(select(ColdStorageStockReport).order_by(ColdStorageStockReport.report_date.desc())).all()
    return [
        {
            "id": r.id,
            "cold_storage_facility_id": r.cold_storage_facility_id,
            "municipality_id": r.municipality_id,
            "reporting_month": r.reporting_month,
            "current_stock_tons": r.current_stock_tons,
            "utilization_pct": r.utilization_pct,
        }
        for r in rows
    ]
