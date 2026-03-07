from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.openapi import router_default_responses
from app.core.rbac import require_role
from app.models import HarvestReport
from app.schemas.auth import CurrentUser
from app.schemas.domain import HarvestReportCreate
from app.schemas.mobile_sync import MobileSubmissionRecord, MobileSyncRequest, MobileSyncResponse
from app.services.audit_service import emit_audit_event
from app.services.mobile_sync_service import list_mobile_submissions, process_mobile_sync_batch
from app.services.production_service import create_harvest_report, list_harvest_reports

router = APIRouter(prefix="/production", tags=["production"], responses=router_default_responses("production"))

MOBILE_SYNC_REQUEST_EXAMPLE: dict[str, Any] = {
    "contract_version": "1.0",
    "sync_batch_id": "mobile-20260306-san-jose-001",
    "provenance": {
        "source_channel": "mobile_app",
        "client_id": "municipal-field-app",
        "device_id": "android-sj-001",
        "app_version": "1.2.0",
        "submitted_at": "2026-03-06T13:41:00Z",
    },
    "submissions": [
        {
            "idempotency_key": "harvest-202603-san-jose-001",
            "submission_type": "harvest_report",
            "observed_server_updated_at": "2026-03-05T10:00:00Z",
            "payload": {
                "municipality_id": 1,
                "farmer_id": 3,
                "reporting_month": "2026-03-01",
                "harvest_date": "2026-03-05",
                "volume_tons": 18.7,
                "quality_grade": "A",
            },
        }
    ],
}


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/harvest-reports")
def get_harvest_reports(
    municipality_id: int | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "executive_viewer", "auditor", "market_analyst"))] = None,
):
    scoped = municipality_id
    if "municipal_encoder" in current_user.roles and current_user.municipality_id:
        scoped = current_user.municipality_id
    rows = list_harvest_reports(db, scoped)
    return [
        {
            "id": r.id,
            "municipality_id": r.municipality_id,
            "reporting_month": r.reporting_month,
            "harvest_date": r.harvest_date,
            "volume_tons": r.volume_tons,
            "quality_grade": r.quality_grade,
        }
        for r in rows
    ]


@router.post("/harvest-reports")
def create_harvest(
    payload: HarvestReportCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder"))],
):
    report = HarvestReport(
        municipality_id=payload.municipality_id,
        farmer_id=payload.farmer_id,
        reporting_month=payload.reporting_month,
        harvest_date=payload.harvest_date,
        volume_tons=payload.volume_tons,
        quality_grade=payload.quality_grade,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    create_harvest_report(db, report)

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="production.harvest.create",
        entity_type="harvest_report",
        entity_id=str(report.id),
        after_payload={"municipality_id": report.municipality_id, "volume_tons": report.volume_tons},
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    return {"id": report.id, "message": "Harvest report recorded"}


@router.post("/mobile-sync", response_model=MobileSyncResponse)
def sync_mobile_submissions(
    payload: Annotated[
        MobileSyncRequest,
        Body(
            openapi_examples={
                "mobileSyncBatch": {
                    "summary": "Mobile client batch sync with idempotent submissions",
                    "value": MOBILE_SYNC_REQUEST_EXAMPLE,
                }
            }
        ),
    ],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "municipal_encoder", "warehouse_operator"))],
):
    request_ip = _request_ip(request)
    user_agent = request.headers.get("user-agent")

    response = process_mobile_sync_batch(
        db,
        payload=payload,
        current_user=current_user,
        correlation_id=getattr(request.state, "correlation_id", None),
        request_ip=request_ip,
        user_agent=user_agent,
    )

    provenance = payload.provenance.model_dump(exclude_none=True, mode="json")
    for result in response.results:
        emit_audit_event(
            db,
            actor_user_id=current_user.id,
            action_type=f"submission.mobile.{result.status}",
            entity_type="source_submission",
            entity_id=str(result.source_submission_id or result.idempotency_key),
            after_payload={
                "sync_batch_id": payload.sync_batch_id,
                "contract_version": payload.contract_version,
                "status": result.status,
                "submission_type": result.submission_type,
                "idempotency_key": result.idempotency_key,
                "source_submission_id": result.source_submission_id,
                "target_entity_type": result.entity_type,
                "target_entity_id": result.entity_id,
                "conflict_reason": result.conflict_reason,
            },
            correlation_id=getattr(request.state, "correlation_id", None),
            metadata={
                "provenance": provenance,
                "source_channel": payload.provenance.source_channel,
                "client_id": payload.provenance.client_id,
                "device_id": payload.provenance.device_id,
                "app_version": payload.provenance.app_version,
                "request_ip": request_ip,
                "user_agent": user_agent,
            },
        )

    emit_audit_event(
        db,
        actor_user_id=current_user.id,
        action_type="submission.mobile.batch.process",
        entity_type="source_submission_batch",
        entity_id=payload.sync_batch_id,
        after_payload={
            "sync_batch_id": payload.sync_batch_id,
            "contract_version": payload.contract_version,
            "submitted_items": len(payload.submissions),
            "summary": response.summary,
        },
        correlation_id=getattr(request.state, "correlation_id", None),
        metadata={
            "provenance": provenance,
            "source_channel": payload.provenance.source_channel,
            "client_id": payload.provenance.client_id,
            "device_id": payload.provenance.device_id,
            "app_version": payload.provenance.app_version,
        },
    )

    return response


@router.get("/mobile-sync/submissions", response_model=list[MobileSubmissionRecord])
def get_mobile_submission_history(
    status: str | None = Query(default=None),
    sync_batch_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[CurrentUser, Depends(require_role("super_admin", "provincial_admin", "auditor", "municipal_encoder", "warehouse_operator"))] = None,
):
    scoped_actor_id = current_user.id if set(current_user.roles).intersection({"municipal_encoder", "warehouse_operator"}) else None
    return list_mobile_submissions(
        db,
        status=status,
        sync_batch_id=sync_batch_id,
        submitted_by=scoped_actor_id,
        limit=limit,
    )
