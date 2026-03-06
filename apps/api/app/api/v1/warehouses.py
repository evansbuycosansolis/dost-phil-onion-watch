from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import Warehouse, WarehouseStockReport
from app.schemas.auth import CurrentUser
from app.schemas.domain import WarehouseCreate, WarehouseStockReportCreate
from app.services.audit_service import emit_audit_event
from app.services.warehouse_service import (
    create_warehouse,
    create_warehouse_stock_report,
    list_warehouse_stock_reports,
    list_warehouses,
)

router = APIRouter(prefix="/warehouses", tags=["warehouses"], responses=router_default_responses("warehouses"))


@router.get("/")
def get_warehouses(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "market_analyst", "executive_viewer", "auditor"))],
):
    municipality_id = current_user.municipality_id if "warehouse_operator" in current_user.roles else None
    rows = list_warehouses(db, municipality_id)
    return [
        {
            "id": r.id,
            "name": r.name,
            "municipality_id": r.municipality_id,
            "location": r.location,
            "capacity_tons": r.capacity_tons,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/")
def create_warehouse_endpoint(
    payload: WarehouseCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin"))],
):
    warehouse = Warehouse(
        municipality_id=payload.municipality_id,
        name=payload.name,
        location=payload.location,
        capacity_tons=payload.capacity_tons,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_warehouse(db, warehouse)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        after_payload={"municipality_id": warehouse.municipality_id, "capacity_tons": warehouse.capacity_tons},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": warehouse.id, "name": warehouse.name}


@router.get("/stock-reports")
def get_stock_reports(
    warehouse_id: int | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator", "auditor", "market_analyst", "executive_viewer"))] = None,
):
    rows = list_warehouse_stock_reports(db, warehouse_id)
    return [
        {
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "municipality_id": r.municipality_id,
            "reporting_month": r.reporting_month,
            "report_date": r.report_date,
            "current_stock_tons": r.current_stock_tons,
            "inflow_tons": r.inflow_tons,
            "outflow_tons": r.outflow_tons,
        }
        for r in rows
    ]


@router.post("/stock-reports")
def create_stock_report(
    payload: WarehouseStockReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "warehouse_operator"))],
):
    report = WarehouseStockReport(
        warehouse_id=payload.warehouse_id,
        municipality_id=payload.municipality_id,
        reporting_month=payload.reporting_month,
        report_date=payload.report_date,
        current_stock_tons=payload.current_stock_tons,
        inflow_tons=payload.inflow_tons,
        outflow_tons=payload.outflow_tons,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_warehouse_stock_report(db, report)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="warehouse.stock_report.create",
        entity_type="warehouse_stock_report",
        entity_id=str(report.id),
        after_payload={
            "warehouse_id": report.warehouse_id,
            "current_stock_tons": report.current_stock_tons,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": report.id, "message": "Warehouse stock report created"}
