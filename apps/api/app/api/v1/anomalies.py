from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.anomaly import AnomalyRunRequest
from app.schemas.auth import CurrentUser
from app.services.anomaly_service import get_anomaly, list_anomalies, run_anomaly_detection
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/anomalies", tags=["anomalies"], responses=router_default_responses("anomalies"))


@router.get("/")
def anomalies(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = list_anomalies(db)
    return [
        {
            "id": row.id,
            "detected_at": row.detected_at,
            "reporting_month": row.reporting_month,
            "anomaly_type": row.anomaly_type,
            "scope_type": row.scope_type,
            "severity": row.severity,
            "summary": row.summary,
            "municipality_id": row.municipality_id,
            "warehouse_id": row.warehouse_id,
            "market_id": row.market_id,
            "metrics": row.supporting_metrics_json,
        }
        for row in rows
    ]


@router.post("/run")
def run_anomalies(
    payload: AnomalyRunRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst"))],
):
    month = payload.reporting_month or date.today().replace(day=1)
    events = run_anomaly_detection(db, month)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="anomaly.run",
        entity_type="anomaly_batch",
        entity_id=month.isoformat(),
        after_payload={"created": len(events), "reporting_month": month.isoformat()},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"created": len(events), "reporting_month": month}


@router.get("/{anomaly_id}")
def anomaly_detail(
    anomaly_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    row = get_anomaly(db, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return {
        "id": row.id,
        "detected_at": row.detected_at,
        "reporting_month": row.reporting_month,
        "anomaly_type": row.anomaly_type,
        "scope_type": row.scope_type,
        "severity": row.severity,
        "summary": row.summary,
        "municipality_id": row.municipality_id,
        "warehouse_id": row.warehouse_id,
        "market_id": row.market_id,
        "metrics": row.supporting_metrics_json,
    }
