from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import ForecastRun
from app.schemas.auth import CurrentUser
from app.schemas.forecasting import (
    ForecastDiagnosticsDTO,
    ForecastLatestResponse,
    ForecastOutputDTO,
    ForecastRunDTO,
    ForecastRunRequest,
    ForecastRunResult,
)
from app.services.audit_service import emit_audit_event
from app.services.forecasting_service import (
    build_run_model_diagnostics,
    forecast_history,
    get_forecast_outputs,
    get_latest_forecast_run,
    latest_model_diagnostics,
    run_forecasting,
)

router = APIRouter(prefix="/forecasting", tags=["forecasting"], responses=router_default_responses("forecasting"))

READ_ROLES = ("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")
RUN_ROLES = ("super_admin", "provincial_admin", "market_analyst")


@router.post("/run", response_model=ForecastRunResult)
def run_forecast(
    payload: ForecastRunRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*RUN_ROLES))],
):
    month = payload.run_month or date.today().replace(day=1)
    run = run_forecasting(db, month)
    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="forecast.run",
        entity_type="forecast_run",
        entity_id=str(run.id),
        after_payload={"run_month": str(run.run_month), "status": run.status, "model_used": run.model_used},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return ForecastRunResult(run_id=run.id, status=run.status)


@router.get("/latest", response_model=ForecastLatestResponse)
def latest_forecast(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = get_latest_forecast_run(db)
    if not run:
        return ForecastLatestResponse(run=None, outputs=[], diagnostics=None)

    outputs = get_forecast_outputs(db, run.id)
    diagnostics = build_run_model_diagnostics(db, run.id)
    return ForecastLatestResponse(
        run=ForecastRunDTO(
            id=run.id,
            run_at=run.run_at,
            run_month=run.run_month,
            model_used=run.model_used,
            status=run.status,
            metrics=run.metrics_json,
        ),
        outputs=[
            ForecastOutputDTO(
                id=output.id,
                municipality_id=output.municipality_id,
                period_start=output.period_start,
                period_end=output.period_end,
                next_month_supply_tons=output.next_month_supply_tons,
                next_quarter_trend=output.next_quarter_trend,
                shortage_probability=output.shortage_probability,
                oversupply_probability=output.oversupply_probability,
                confidence_score=output.confidence_score,
                selected_model=output.selected_model,
                selected_model_score=output.selected_model_score,
                fallback_order=list(output.fallback_order_json or []),
            )
            for output in outputs
        ],
        diagnostics=ForecastDiagnosticsDTO(**diagnostics),
    )


@router.get("/history", response_model=list[ForecastRunDTO])
def get_history(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = forecast_history(db, limit=24)
    return [
        ForecastRunDTO(
            id=row.id,
            run_at=row.run_at,
            run_month=row.run_month,
            model_used=row.model_used,
            status=row.status,
            metrics=row.metrics_json,
        )
        for row in rows
    ]


@router.get("/diagnostics/latest", response_model=ForecastDiagnosticsDTO)
def latest_diagnostics(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    diagnostics = latest_model_diagnostics(db)
    return ForecastDiagnosticsDTO(**diagnostics)


@router.get("/diagnostics/{run_id}", response_model=ForecastDiagnosticsDTO)
def run_diagnostics(
    run_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    run = db.scalar(select(ForecastRun).where(ForecastRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Forecast run not found")
    diagnostics = build_run_model_diagnostics(db, run_id)
    return ForecastDiagnosticsDTO(**diagnostics)
