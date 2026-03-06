from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.auth import CurrentUser
from app.schemas.forecasting import ForecastRunRequest
from app.services.audit_service import emit_audit_event
from app.services.forecasting_service import forecast_history, get_forecast_outputs, get_latest_forecast_run, run_forecasting

router = APIRouter(prefix="/forecasting", tags=["forecasting"], responses=router_default_responses("forecasting"))


@router.post("/run")
def run_forecast(
    payload: ForecastRunRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst"))],
):
    month = payload.run_month or date.today().replace(day=1)
    run = run_forecasting(db, month)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="forecast.run",
        entity_type="forecast_run",
        entity_id=str(run.id),
        after_payload={"run_month": str(run.run_month), "status": run.status},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return {"run_id": run.id, "status": run.status}


@router.get("/latest")
def latest_forecast(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    run = get_latest_forecast_run(db)
    if not run:
        return {"run": None, "outputs": []}
    outputs = get_forecast_outputs(db, run.id)
    return {
        "run": {"id": run.id, "run_month": run.run_month, "model_used": run.model_used, "status": run.status},
        "outputs": [
            {
                "id": o.id,
                "municipality_id": o.municipality_id,
                "period_start": o.period_start,
                "period_end": o.period_end,
                "next_month_supply_tons": o.next_month_supply_tons,
                "next_quarter_trend": o.next_quarter_trend,
                "shortage_probability": o.shortage_probability,
                "oversupply_probability": o.oversupply_probability,
                "confidence_score": o.confidence_score,
            }
            for o in outputs
        ],
    }


@router.get("/history")
def get_history(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor"))],
):
    rows = forecast_history(db, limit=24)
    return [
        {
            "id": r.id,
            "run_at": r.run_at,
            "run_month": r.run_month,
            "model_used": r.model_used,
            "status": r.status,
            "metrics": r.metrics_json,
        }
        for r in rows
    ]
