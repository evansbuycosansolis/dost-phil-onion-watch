from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import FarmgatePriceReport, RetailPriceReport, WholesalePriceReport
from app.schemas.auth import CurrentUser
from app.schemas.domain import PriceReportCreate
from app.services.audit_service import emit_audit_event
from app.services.pricing_service import (
    create_farmgate_price,
    create_retail_price,
    create_wholesale_price,
    list_farmgate_prices,
)

router = APIRouter(prefix="/prices", tags=["prices"], responses=router_default_responses("prices"))


@router.get("/farmgate")
def get_farmgate(
    municipality_id: int | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "municipal_encoder", "executive_viewer", "auditor"))] = None,
):
    scoped = municipality_id
    if "municipal_encoder" in current_user.roles and current_user.municipality_id:
        scoped = current_user.municipality_id
    rows = list_farmgate_prices(db, scoped)
    return [
        {
            "id": r.id,
            "municipality_id": r.municipality_id,
            "report_date": r.report_date,
            "reporting_month": r.reporting_month,
            "price_per_kg": r.price_per_kg,
        }
        for r in rows
    ]


@router.post("/farmgate")
def create_farmgate(
    payload: PriceReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "municipal_encoder"))],
):
    record = FarmgatePriceReport(
        municipality_id=payload.municipality_id,
        report_date=payload.report_date,
        reporting_month=payload.reporting_month,
        price_per_kg=payload.price_per_kg,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_farmgate_price(db, record)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="prices.farmgate.create",
        entity_type="farmgate_price_report",
        entity_id=str(record.id),
        after_payload={"municipality_id": record.municipality_id, "price_per_kg": record.price_per_kg},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"id": record.id}


@router.post("/wholesale")
def create_wholesale(
    payload: PriceReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst"))],
):
    record = WholesalePriceReport(
        municipality_id=payload.municipality_id,
        report_date=payload.report_date,
        reporting_month=payload.reporting_month,
        price_per_kg=payload.price_per_kg,
        market_id=payload.market_id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_wholesale_price(db, record)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="prices.wholesale.create",
        entity_type="wholesale_price_report",
        entity_id=str(record.id),
        after_payload={"municipality_id": record.municipality_id, "price_per_kg": record.price_per_kg},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"id": record.id}


@router.post("/retail")
def create_retail(
    payload: PriceReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst"))],
):
    record = RetailPriceReport(
        municipality_id=payload.municipality_id,
        report_date=payload.report_date,
        reporting_month=payload.reporting_month,
        price_per_kg=payload.price_per_kg,
        market_id=payload.market_id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_retail_price(db, record)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="prices.retail.create",
        entity_type="retail_price_report",
        entity_id=str(record.id),
        after_payload={"municipality_id": record.municipality_id, "price_per_kg": record.price_per_kg},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"id": record.id}
