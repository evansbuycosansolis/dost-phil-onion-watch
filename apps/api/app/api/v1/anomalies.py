from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.schemas.anomaly import (
    AnomalyDTO,
    AnomalyRunRequest,
    AnomalyRunResponse,
    AnomalyThresholdConfigDTO,
    AnomalyThresholdUpdateRequest,
    AnomalyThresholdVersionDTO,
)
from app.schemas.auth import CurrentUser
from app.services.anomaly_service import (
    get_anomaly,
    get_threshold_config,
    list_anomalies,
    list_threshold_configs,
    list_threshold_versions,
    run_anomaly_detection,
    supported_anomaly_types,
    update_threshold_config,
)
from app.services.audit_service import emit_audit_event

router = APIRouter(prefix="/anomalies", tags=["anomalies"], responses=router_default_responses("anomalies"))

READ_ROLES = ("super_admin", "provincial_admin", "market_analyst", "policy_reviewer", "executive_viewer", "auditor")
RUN_ROLES = ("super_admin", "provincial_admin", "market_analyst")
TUNE_ROLES = ("super_admin", "provincial_admin", "market_analyst")


def _anomaly_to_dto(row) -> AnomalyDTO:
    return AnomalyDTO(
        id=row.id,
        detected_at=row.detected_at,
        reporting_month=row.reporting_month,
        anomaly_type=row.anomaly_type,
        scope_type=row.scope_type,
        severity=row.severity,
        summary=row.summary,
        municipality_id=row.municipality_id,
        warehouse_id=row.warehouse_id,
        market_id=row.market_id,
        metrics=row.supporting_metrics_json or {},
    )


def _config_to_dto(config) -> AnomalyThresholdConfigDTO:
    return AnomalyThresholdConfigDTO(
        id=config.id,
        anomaly_type=config.anomaly_type,
        version=config.version,
        thresholds=config.thresholds_json or {},
        is_active=config.is_active,
        change_reason=config.change_reason,
        last_changed_by=config.last_changed_by,
        updated_at=config.updated_at,
    )


@router.get("/", response_model=list[AnomalyDTO])
def anomalies(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    rows = list_anomalies(db)
    return [_anomaly_to_dto(row) for row in rows]


@router.post("/run", response_model=AnomalyRunResponse)
def run_anomalies(
    payload: AnomalyRunRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*RUN_ROLES))],
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

    return AnomalyRunResponse(created=len(events), reporting_month=month)


@router.get("/thresholds", response_model=list[AnomalyThresholdConfigDTO])
def thresholds(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    return [_config_to_dto(config) for config in list_threshold_configs(db)]


@router.get("/thresholds/{anomaly_type}", response_model=AnomalyThresholdConfigDTO)
def threshold_detail(
    anomaly_type: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    config = get_threshold_config(db, anomaly_type)
    if not config:
        raise HTTPException(status_code=404, detail=f"Threshold config not found for anomaly type: {anomaly_type}")
    return _config_to_dto(config)


@router.get("/thresholds/{anomaly_type}/versions", response_model=list[AnomalyThresholdVersionDTO])
def threshold_versions(
    anomaly_type: str,
    limit: int = 25,
    db: Annotated[Session, Depends(get_db)] = None,
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))] = None,
):
    if anomaly_type not in supported_anomaly_types():
        raise HTTPException(status_code=404, detail=f"Unsupported anomaly type: {anomaly_type}")

    rows = list_threshold_versions(db, anomaly_type, limit=max(1, min(limit, 100)))
    return [
        AnomalyThresholdVersionDTO(
            id=row.id,
            anomaly_type=row.anomaly_type,
            version=row.version,
            thresholds=row.thresholds_json or {},
            changed_by=row.changed_by,
            change_reason=row.change_reason,
            changed_at=row.changed_at,
        )
        for row in rows
    ]


@router.post("/thresholds/{anomaly_type}", response_model=AnomalyThresholdConfigDTO)
def update_thresholds(
    anomaly_type: str,
    payload: AnomalyThresholdUpdateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role(*TUNE_ROLES))],
):
    if anomaly_type not in supported_anomaly_types():
        raise HTTPException(status_code=404, detail=f"Unsupported anomaly type: {anomaly_type}")

    try:
        config, before, after = update_threshold_config(
            db,
            anomaly_type=anomaly_type,
            thresholds_patch=payload.thresholds,
            changed_by=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="anomaly.threshold.update",
        entity_type="anomaly_threshold_config",
        entity_id=str(config.id),
        before_payload={"anomaly_type": anomaly_type, "version": config.version - 1, "thresholds": before},
        after_payload={"anomaly_type": anomaly_type, "version": config.version, "thresholds": after, "reason": payload.reason},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return _config_to_dto(config)


@router.get("/{anomaly_id}", response_model=AnomalyDTO)
def anomaly_detail(
    anomaly_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_role(*READ_ROLES))],
):
    row = get_anomaly(db, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return _anomaly_to_dto(row)
