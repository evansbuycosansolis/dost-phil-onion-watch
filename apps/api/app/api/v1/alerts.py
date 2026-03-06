from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.alerts import AlertActionRequest
from app.schemas.auth import CurrentUser
from app.services.alert_service import acknowledge_alert, get_alert, list_alerts, resolve_alert
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/alerts", tags=["alerts"], responses=router_default_responses("alerts"))


@router.get("/")
def alerts(
    status: str | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor", "municipal_encoder", "warehouse_operator"))] = None,
):
    rows = list_alerts(db, status)
    if ("municipal_encoder" in current_user.roles or "warehouse_operator" in current_user.roles) and current_user.municipality_id:
        rows = [r for r in rows if r.municipality_id == current_user.municipality_id or r.municipality_id is None]
    return [
        {
            "id": a.id,
            "title": a.title,
            "severity": a.severity,
            "alert_type": a.alert_type,
            "scope_type": a.scope_type,
            "status": a.status,
            "summary": a.summary,
            "recommended_action": a.recommended_action,
            "municipality_id": a.municipality_id,
            "warehouse_id": a.warehouse_id,
            "market_id": a.market_id,
            "linked_forecast_id": a.linked_forecast_id,
            "linked_anomaly_id": a.linked_anomaly_id,
            "opened_at": a.opened_at,
        }
        for a in rows
    ]


@router.get("/{alert_id}")
def alert_detail(
    alert_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor", "municipal_encoder", "warehouse_operator"))],
):
    alert = get_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if ("municipal_encoder" in current_user.roles or "warehouse_operator" in current_user.roles) and current_user.municipality_id:
        if alert.municipality_id not in {None, current_user.municipality_id}:
            raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "id": alert.id,
        "title": alert.title,
        "severity": alert.severity,
        "alert_type": alert.alert_type,
        "scope_type": alert.scope_type,
        "status": alert.status,
        "summary": alert.summary,
        "recommended_action": alert.recommended_action,
        "municipality_id": alert.municipality_id,
        "warehouse_id": alert.warehouse_id,
        "market_id": alert.market_id,
        "linked_forecast_id": alert.linked_forecast_id,
        "linked_anomaly_id": alert.linked_anomaly_id,
        "opened_at": alert.opened_at,
    }


@router.post("/{alert_id}/acknowledge")
def acknowledge(
    alert_id: int,
    payload: AlertActionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "municipal_encoder", "warehouse_operator"))],
):
    alert = get_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    before = {"status": alert.status}
    alert = acknowledge_alert(db, alert, current_user.id, payload.notes)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="alert.acknowledge",
        entity_type="alert",
        entity_id=str(alert.id),
        before_payload=before,
        after_payload={"status": alert.status, "notes": payload.notes},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": alert.id, "status": alert.status}


@router.post("/{alert_id}/resolve")
def resolve(
    alert_id: int,
    payload: AlertActionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "policy_reviewer", "market_analyst"))],
):
    alert = get_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    before = {"status": alert.status}
    alert = resolve_alert(db, alert, current_user.id, payload.notes)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="alert.resolve",
        entity_type="alert",
        entity_id=str(alert.id),
        before_payload=before,
        after_payload={"status": alert.status, "notes": payload.notes},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": alert.id, "status": alert.status}
