from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FarmgatePriceReport, HarvestReport, SourceSubmission, Warehouse, WarehouseStockReport
from app.schemas.auth import CurrentUser
from app.schemas.domain import HarvestReportCreate, PriceReportCreate, WarehouseStockReportCreate
from app.schemas.mobile_sync import (
    MobileSubmissionItem,
    MobileSubmissionProvenance,
    MobileSubmissionRecord,
    MobileSubmissionResult,
    MobileSyncRequest,
    MobileSyncResponse,
)


@dataclass
class _ApplyResult:
    status: str
    entity_type: str
    entity_id: str
    server_updated_at: datetime | None


class MobileSubmissionConflictError(ValueError):
    pass


class MobileSubmissionValidationError(ValueError):
    pass


_SCOPED_ROLES = {"municipal_encoder", "warehouse_operator"}


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _source_name(provenance: MobileSubmissionProvenance) -> str:
    raw = f"{provenance.client_id}:{provenance.device_id}"
    return raw[:120]


def _scope_guard(user: CurrentUser, municipality_id: int) -> None:
    if user.municipality_id and set(user.roles).intersection(_SCOPED_ROLES):
        if municipality_id != user.municipality_id:
            raise MobileSubmissionValidationError(
                f"municipality scope violation: user scoped to {user.municipality_id}, payload has {municipality_id}"
            )


def _check_conflict(existing_updated_at: datetime | None, observed_server_updated_at: datetime | None) -> None:
    if existing_updated_at is None or observed_server_updated_at is None:
        return
    observed = _normalize_datetime(observed_server_updated_at)
    if observed is None:
        return
    # Small tolerance for clock jitter between client and server.
    if existing_updated_at > observed + timedelta(seconds=1):
        raise MobileSubmissionConflictError("stale_observed_server_updated_at")


def _apply_harvest_report(
    db: Session,
    *,
    payload: dict[str, Any],
    observed_server_updated_at: datetime | None,
    current_user: CurrentUser,
) -> _ApplyResult:
    data = HarvestReportCreate(**payload)
    _scope_guard(current_user, data.municipality_id)

    stmt = select(HarvestReport).where(
        HarvestReport.municipality_id == data.municipality_id,
        HarvestReport.reporting_month == data.reporting_month,
        HarvestReport.harvest_date == data.harvest_date,
    )
    if data.farmer_id is None:
        stmt = stmt.where(HarvestReport.farmer_id.is_(None))
    else:
        stmt = stmt.where(HarvestReport.farmer_id == data.farmer_id)

    existing = db.scalar(stmt.order_by(HarvestReport.id.desc()).limit(1))
    if existing is None:
        row = HarvestReport(
            municipality_id=data.municipality_id,
            farmer_id=data.farmer_id,
            reporting_month=data.reporting_month,
            harvest_date=data.harvest_date,
            volume_tons=data.volume_tons,
            quality_grade=data.quality_grade,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(row)
        db.flush()
        return _ApplyResult("accepted", "harvest_report", str(row.id), row.updated_at)

    _check_conflict(existing.updated_at, observed_server_updated_at)
    existing.volume_tons = data.volume_tons
    existing.quality_grade = data.quality_grade
    existing.updated_by = current_user.id
    db.flush()
    return _ApplyResult("updated", "harvest_report", str(existing.id), existing.updated_at)


def _apply_warehouse_stock_report(
    db: Session,
    *,
    payload: dict[str, Any],
    observed_server_updated_at: datetime | None,
    current_user: CurrentUser,
) -> _ApplyResult:
    data = WarehouseStockReportCreate(**payload)
    _scope_guard(current_user, data.municipality_id)

    warehouse = db.scalar(select(Warehouse).where(Warehouse.id == data.warehouse_id))
    if warehouse is None:
        raise MobileSubmissionValidationError(f"warehouse not found: {data.warehouse_id}")
    if warehouse.municipality_id != data.municipality_id:
        raise MobileSubmissionValidationError(
            f"warehouse municipality mismatch: warehouse={warehouse.municipality_id}, payload={data.municipality_id}"
        )

    existing = db.scalar(
        select(WarehouseStockReport)
        .where(
            WarehouseStockReport.warehouse_id == data.warehouse_id,
            WarehouseStockReport.reporting_month == data.reporting_month,
            WarehouseStockReport.report_date == data.report_date,
        )
        .order_by(WarehouseStockReport.id.desc())
        .limit(1)
    )

    if existing is None:
        row = WarehouseStockReport(
            warehouse_id=data.warehouse_id,
            municipality_id=data.municipality_id,
            reporting_month=data.reporting_month,
            report_date=data.report_date,
            current_stock_tons=data.current_stock_tons,
            inflow_tons=data.inflow_tons,
            outflow_tons=data.outflow_tons,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(row)
        db.flush()
        return _ApplyResult("accepted", "warehouse_stock_report", str(row.id), row.updated_at)

    _check_conflict(existing.updated_at, observed_server_updated_at)
    existing.current_stock_tons = data.current_stock_tons
    existing.inflow_tons = data.inflow_tons
    existing.outflow_tons = data.outflow_tons
    existing.updated_by = current_user.id
    db.flush()
    return _ApplyResult("updated", "warehouse_stock_report", str(existing.id), existing.updated_at)


def _apply_farmgate_price_report(
    db: Session,
    *,
    payload: dict[str, Any],
    observed_server_updated_at: datetime | None,
    current_user: CurrentUser,
) -> _ApplyResult:
    data = PriceReportCreate(**payload)
    _scope_guard(current_user, data.municipality_id)

    existing = db.scalar(
        select(FarmgatePriceReport)
        .where(
            FarmgatePriceReport.municipality_id == data.municipality_id,
            FarmgatePriceReport.report_date == data.report_date,
            FarmgatePriceReport.reporting_month == data.reporting_month,
        )
        .order_by(FarmgatePriceReport.id.desc())
        .limit(1)
    )
    if existing is None:
        row = FarmgatePriceReport(
            municipality_id=data.municipality_id,
            report_date=data.report_date,
            reporting_month=data.reporting_month,
            price_per_kg=data.price_per_kg,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(row)
        db.flush()
        return _ApplyResult("accepted", "farmgate_price_report", str(row.id), row.updated_at)

    _check_conflict(existing.updated_at, observed_server_updated_at)
    existing.price_per_kg = data.price_per_kg
    existing.updated_by = current_user.id
    db.flush()
    return _ApplyResult("updated", "farmgate_price_report", str(existing.id), existing.updated_at)


def _apply_submission(
    db: Session,
    *,
    item: MobileSubmissionItem,
    current_user: CurrentUser,
) -> _ApplyResult:
    if item.submission_type == "harvest_report":
        return _apply_harvest_report(
            db,
            payload=item.payload,
            observed_server_updated_at=item.observed_server_updated_at,
            current_user=current_user,
        )
    if item.submission_type == "warehouse_stock_report":
        return _apply_warehouse_stock_report(
            db,
            payload=item.payload,
            observed_server_updated_at=item.observed_server_updated_at,
            current_user=current_user,
        )
    if item.submission_type == "farmgate_price_report":
        return _apply_farmgate_price_report(
            db,
            payload=item.payload,
            observed_server_updated_at=item.observed_server_updated_at,
            current_user=current_user,
        )
    raise MobileSubmissionValidationError(f"unsupported submission_type: {item.submission_type}")


def process_mobile_sync_batch(
    db: Session,
    *,
    payload: MobileSyncRequest,
    current_user: CurrentUser,
    correlation_id: str | None,
    request_ip: str | None,
    user_agent: str | None,
) -> MobileSyncResponse:
    source_name = _source_name(payload.provenance)
    batch_submitted_at = _normalize_datetime(payload.provenance.submitted_at) or datetime.now(timezone.utc)

    results: list[MobileSubmissionResult] = []
    counters: dict[str, int] = {"accepted": 0, "updated": 0, "duplicate": 0, "conflict": 0, "rejected": 0}

    for item in payload.submissions:
        submission_hash = _payload_hash(item.payload)
        existing = db.scalar(
            select(SourceSubmission)
            .where(
                SourceSubmission.source_name == source_name,
                SourceSubmission.idempotency_key == item.idempotency_key,
            )
            .order_by(SourceSubmission.id.desc())
            .limit(1)
        )

        if existing is not None:
            if existing.payload_hash == submission_hash:
                result = MobileSubmissionResult(
                    idempotency_key=item.idempotency_key,
                    submission_type=item.submission_type,
                    status="duplicate",
                    source_submission_id=existing.id,
                    entity_type=existing.target_entity_type,
                    entity_id=existing.target_entity_id,
                    conflict_reason=existing.conflict_reason,
                    message="Already processed",
                )
                counters["duplicate"] += 1
                results.append(result)
                continue

            result = MobileSubmissionResult(
                idempotency_key=item.idempotency_key,
                submission_type=item.submission_type,
                status="conflict",
                source_submission_id=existing.id,
                conflict_reason="idempotency_key_reuse_with_different_payload",
                message="Idempotency key already used with different payload",
            )
            counters["conflict"] += 1
            results.append(result)
            continue

        source_submission = SourceSubmission(
            submission_type=item.submission_type,
            source_name=source_name,
            source_channel=payload.provenance.source_channel,
            client_id=payload.provenance.client_id,
            device_id=payload.provenance.device_id,
            app_version=payload.provenance.app_version,
            sync_batch_id=payload.sync_batch_id,
            idempotency_key=item.idempotency_key,
            payload_hash=submission_hash,
            submitted_by=current_user.id,
            submitted_at=batch_submitted_at,
            status="processing",
            payload=item.payload,
            provenance_json={
                "contract_version": payload.contract_version,
                "source_channel": payload.provenance.source_channel,
                "client_id": payload.provenance.client_id,
                "device_id": payload.provenance.device_id,
                "app_version": payload.provenance.app_version,
                "sync_batch_id": payload.sync_batch_id,
                "batch_submitted_at": batch_submitted_at.isoformat(),
                "item_observed_server_updated_at": _normalize_datetime(item.observed_server_updated_at).isoformat()
                if _normalize_datetime(item.observed_server_updated_at)
                else None,
                "correlation_id": correlation_id,
                "request_ip": request_ip,
                "user_agent": user_agent,
            },
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(source_submission)
        db.flush()

        try:
            apply_result = _apply_submission(db, item=item, current_user=current_user)
            source_submission.status = apply_result.status
            source_submission.target_entity_type = apply_result.entity_type
            source_submission.target_entity_id = apply_result.entity_id
            source_submission.conflict_reason = None
            source_submission.updated_by = current_user.id
            db.flush()

            result = MobileSubmissionResult(
                idempotency_key=item.idempotency_key,
                submission_type=item.submission_type,
                status=apply_result.status,  # type: ignore[arg-type]
                source_submission_id=source_submission.id,
                entity_type=apply_result.entity_type,
                entity_id=apply_result.entity_id,
                server_updated_at=apply_result.server_updated_at,
                message="Submission synchronized",
            )
            counters[apply_result.status] = counters.get(apply_result.status, 0) + 1
            results.append(result)
        except MobileSubmissionConflictError as exc:
            source_submission.status = "conflict"
            source_submission.conflict_reason = str(exc)
            source_submission.updated_by = current_user.id
            db.flush()

            result = MobileSubmissionResult(
                idempotency_key=item.idempotency_key,
                submission_type=item.submission_type,
                status="conflict",
                source_submission_id=source_submission.id,
                conflict_reason=str(exc),
                message="Server has a newer version; client re-sync required",
            )
            counters["conflict"] += 1
            results.append(result)
        except (MobileSubmissionValidationError, ValueError) as exc:
            source_submission.status = "rejected"
            source_submission.conflict_reason = str(exc)
            source_submission.updated_by = current_user.id
            db.flush()

            result = MobileSubmissionResult(
                idempotency_key=item.idempotency_key,
                submission_type=item.submission_type,
                status="rejected",
                source_submission_id=source_submission.id,
                conflict_reason=str(exc),
                message="Payload validation failed",
            )
            counters["rejected"] += 1
            results.append(result)

    return MobileSyncResponse(
        sync_batch_id=payload.sync_batch_id,
        processed_at=datetime.now(timezone.utc),
        summary=counters,
        results=results,
    )


def list_mobile_submissions(
    db: Session,
    *,
    status: str | None = None,
    sync_batch_id: str | None = None,
    submitted_by: int | None = None,
    limit: int = 200,
) -> list[MobileSubmissionRecord]:
    stmt = (
        select(SourceSubmission)
        .where(SourceSubmission.source_channel.in_(["mobile_app", "mobile", "field_mobile"]))
        .order_by(SourceSubmission.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if status:
        stmt = stmt.where(SourceSubmission.status == status)
    if sync_batch_id:
        stmt = stmt.where(SourceSubmission.sync_batch_id == sync_batch_id)
    if submitted_by is not None:
        stmt = stmt.where(SourceSubmission.submitted_by == submitted_by)

    rows = list(db.scalars(stmt))
    return [
        MobileSubmissionRecord(
            id=row.id,
            sync_batch_id=row.sync_batch_id,
            submission_type=row.submission_type,
            source_channel=row.source_channel,
            source_name=row.source_name,
            client_id=row.client_id,
            device_id=row.device_id,
            app_version=row.app_version,
            idempotency_key=row.idempotency_key,
            status=row.status,
            target_entity_type=row.target_entity_type,
            target_entity_id=row.target_entity_id,
            conflict_reason=row.conflict_reason,
            submitted_by=row.submitted_by,
            submitted_at=row.submitted_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            provenance=row.provenance_json,
        )
        for row in rows
    ]
