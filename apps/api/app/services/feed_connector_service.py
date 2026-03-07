from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ApprovalWorkflow,
    FarmgatePriceReport,
    ImportRecord,
    Municipality,
    SourceSubmission,
    Warehouse,
    WarehouseStockReport,
)
from app.schemas.domain import ImportRecordCreate, PriceReportCreate, WarehouseStockReportCreate

AGENCY_SOURCE_CHANNEL = "agency_feed"
AGENCY_SOURCE_PREFIX = "agency:"


class ConnectorError(ValueError):
    pass


class ConnectorValidationError(ConnectorError):
    pass


class ConnectorNotFoundError(ConnectorError):
    pass


@dataclass(frozen=True)
class ConnectorDefinition:
    key: str
    source_name: str
    display_name: str
    description: str
    submission_types: tuple[str, ...]
    adapter_version: str = "1.0"


@dataclass(frozen=True)
class ConnectorNormalizedRecord:
    external_id: str
    submission_type: str
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]


def _build_source_name(connector_key: str) -> str:
    return f"{AGENCY_SOURCE_PREFIX}{connector_key}"


def _connector_key_from_source(source_name: str) -> str:
    if source_name.startswith(AGENCY_SOURCE_PREFIX):
        return source_name[len(AGENCY_SOURCE_PREFIX) :]
    return source_name


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fixture_root() -> Path:
    configured = Path(settings.agency_feed_fixtures_path)
    if configured.is_absolute():
        return configured
    return (Path(__file__).resolve().parents[4] / configured).resolve()


def _load_csv_rows(file_name: str, limit: int) -> list[dict[str, str]]:
    csv_path = _fixture_root() / file_name
    if not csv_path.exists():
        raise ConnectorValidationError(f"Connector fixture file not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            cleaned = {str(key): (value.strip() if isinstance(value, str) else "") for key, value in row.items()}
            rows.append(cleaned)
            if len(rows) >= limit:
                break
    return rows


def _require_text(record: dict[str, str], key: str) -> str:
    value = (record.get(key) or "").strip()
    if not value:
        raise ConnectorValidationError(f"Missing required field: {key}")
    return value


def _parse_iso_date(value: str, *, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConnectorValidationError(f"Invalid date for {field}: {value}") from exc


def _parse_non_negative_float(value: str, *, field: str, allow_zero: bool = True) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConnectorValidationError(f"Invalid number for {field}: {value}") from exc

    if parsed < 0:
        raise ConnectorValidationError(f"{field} must be non-negative")
    if not allow_zero and parsed <= 0:
        raise ConnectorValidationError(f"{field} must be greater than zero")
    return parsed


def _resolve_municipality(db: Session, municipality_code: str) -> Municipality:
    municipality = db.scalar(select(Municipality).where(Municipality.code == municipality_code))
    if municipality is None:
        raise ConnectorValidationError(f"Unknown municipality_code: {municipality_code}")
    return municipality


class BaseConnectorAdapter:
    definition: ConnectorDefinition
    fixture_file: str

    def pull(self, limit: int) -> list[dict[str, str]]:
        return _load_csv_rows(self.fixture_file, limit=max(1, limit))

    def external_id(self, record: dict[str, str], index: int) -> str:
        external_id = (record.get("external_id") or "").strip()
        if not external_id:
            return f"{self.definition.key}-row-{index:04d}"
        return external_id[:120]

    def normalize(self, db: Session, record: dict[str, str], index: int) -> ConnectorNormalizedRecord:
        raise NotImplementedError


class DAPriceFeedAdapter(BaseConnectorAdapter):
    definition = ConnectorDefinition(
        key="da_price_feed",
        source_name=_build_source_name("da_price_feed"),
        display_name="DA Farmgate Price Feed",
        description="Department of Agriculture farmgate price feed for municipal market monitoring.",
        submission_types=("farmgate_price_report",),
    )
    fixture_file = "da_price_feed.csv"

    def normalize(self, db: Session, record: dict[str, str], index: int) -> ConnectorNormalizedRecord:
        municipality_code = _require_text(record, "municipality_code")
        municipality = _resolve_municipality(db, municipality_code)

        report_date = _parse_iso_date(_require_text(record, "report_date"), field="report_date")
        reporting_month = _parse_iso_date(_require_text(record, "reporting_month"), field="reporting_month")
        price_per_kg = _parse_non_negative_float(_require_text(record, "price_per_kg"), field="price_per_kg", allow_zero=False)
        external_id = self.external_id(record, index)

        normalized = {
            "municipality_id": municipality.id,
            "report_date": report_date.isoformat(),
            "reporting_month": reporting_month.isoformat(),
            "price_per_kg": round(price_per_kg, 4),
        }
        return ConnectorNormalizedRecord(
            external_id=external_id,
            submission_type="farmgate_price_report",
            raw_payload=record,
            normalized_payload=normalized,
        )


class BOCImportFeedAdapter(BaseConnectorAdapter):
    definition = ConnectorDefinition(
        key="boc_import_feed",
        source_name=_build_source_name("boc_import_feed"),
        display_name="BOC Import Arrival Feed",
        description="Bureau of Customs shipment arrival feed for onion import visibility.",
        submission_types=("import_record",),
    )
    fixture_file = "boc_import_feed.csv"

    def normalize(self, db: Session, record: dict[str, str], index: int) -> ConnectorNormalizedRecord:
        external_id = self.external_id(record, index)
        import_reference = _require_text(record, "import_reference")
        origin_country = _require_text(record, "origin_country")
        arrival_date = _parse_iso_date(_require_text(record, "arrival_date"), field="arrival_date")
        reporting_month = _parse_iso_date(_require_text(record, "reporting_month"), field="reporting_month")
        volume_tons = _parse_non_negative_float(_require_text(record, "volume_tons"), field="volume_tons", allow_zero=False)
        status = _require_text(record, "status")

        normalized = {
            "import_reference": import_reference,
            "origin_country": origin_country,
            "arrival_date": arrival_date.isoformat(),
            "reporting_month": reporting_month.isoformat(),
            "volume_tons": round(volume_tons, 4),
            "status": status,
        }
        return ConnectorNormalizedRecord(
            external_id=external_id,
            submission_type="import_record",
            raw_payload=record,
            normalized_payload=normalized,
        )


class NFAWarehouseStockFeedAdapter(BaseConnectorAdapter):
    definition = ConnectorDefinition(
        key="nfa_warehouse_stock_feed",
        source_name=_build_source_name("nfa_warehouse_stock_feed"),
        display_name="NFA Warehouse Stock Feed",
        description="National Food Authority warehouse stock feed for release and utilization monitoring.",
        submission_types=("warehouse_stock_report",),
    )
    fixture_file = "nfa_warehouse_stock_feed.csv"

    def normalize(self, db: Session, record: dict[str, str], index: int) -> ConnectorNormalizedRecord:
        external_id = self.external_id(record, index)
        municipality_code = _require_text(record, "municipality_code")
        municipality = _resolve_municipality(db, municipality_code)
        warehouse_name = _require_text(record, "warehouse_name")
        warehouse = db.scalar(
            select(Warehouse).where(
                Warehouse.municipality_id == municipality.id,
                Warehouse.name == warehouse_name,
            )
        )
        if warehouse is None:
            raise ConnectorValidationError(
                f"Unknown warehouse '{warehouse_name}' in municipality_code={municipality_code}"
            )

        report_date = _parse_iso_date(_require_text(record, "report_date"), field="report_date")
        reporting_month = _parse_iso_date(_require_text(record, "reporting_month"), field="reporting_month")
        current_stock_tons = _parse_non_negative_float(
            _require_text(record, "current_stock_tons"),
            field="current_stock_tons",
        )
        inflow_tons = _parse_non_negative_float(_require_text(record, "inflow_tons"), field="inflow_tons")
        outflow_tons = _parse_non_negative_float(_require_text(record, "outflow_tons"), field="outflow_tons")

        normalized = {
            "warehouse_id": warehouse.id,
            "municipality_id": municipality.id,
            "report_date": report_date.isoformat(),
            "reporting_month": reporting_month.isoformat(),
            "current_stock_tons": round(current_stock_tons, 4),
            "inflow_tons": round(inflow_tons, 4),
            "outflow_tons": round(outflow_tons, 4),
        }
        return ConnectorNormalizedRecord(
            external_id=external_id,
            submission_type="warehouse_stock_report",
            raw_payload=record,
            normalized_payload=normalized,
        )


CONNECTOR_ADAPTERS: dict[str, BaseConnectorAdapter] = {
    "da_price_feed": DAPriceFeedAdapter(),
    "boc_import_feed": BOCImportFeedAdapter(),
    "nfa_warehouse_stock_feed": NFAWarehouseStockFeedAdapter(),
}


def list_connector_definitions() -> list[ConnectorDefinition]:
    return [adapter.definition for adapter in CONNECTOR_ADAPTERS.values()]


def get_connector_definition(connector_key: str) -> ConnectorDefinition:
    adapter = CONNECTOR_ADAPTERS.get(connector_key)
    if adapter is None:
        raise ConnectorNotFoundError(f"Unknown connector: {connector_key}")
    return adapter.definition


def _find_source_submission(db: Session, *, source_name: str, idempotency_key: str) -> SourceSubmission | None:
    return db.scalar(
        select(SourceSubmission)
        .where(
            SourceSubmission.source_name == source_name,
            SourceSubmission.idempotency_key == idempotency_key,
        )
        .order_by(SourceSubmission.id.desc())
        .limit(1)
    )


def _status_from_existing(existing: SourceSubmission, payload_hash: str) -> tuple[str, str | None]:
    if existing.payload_hash == payload_hash:
        return "duplicate", None
    return "conflict", "idempotency_key_reuse_with_different_payload"


def run_connector_ingestion(
    db: Session,
    *,
    connector_key: str,
    actor_user_id: int | None,
    correlation_id: str | None,
    limit: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    adapter = CONNECTOR_ADAPTERS.get(connector_key)
    if adapter is None:
        raise ConnectorNotFoundError(f"Unknown connector: {connector_key}")

    sync_batch_id = f"feed-{connector_key}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    rows = adapter.pull(limit=max(1, min(limit, 2000)))
    summary = {
        "connector_key": connector_key,
        "sync_batch_id": sync_batch_id,
        "dry_run": dry_run,
        "fetched_count": len(rows),
        "accepted_count": 0,
        "rejected_count": 0,
        "duplicate_count": 0,
        "conflict_count": 0,
        "pending_approval_count": 0,
        "workflow_created_count": 0,
    }
    results: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        external_id = adapter.external_id(row, index)
        source_name = adapter.definition.source_name

        try:
            normalized = adapter.normalize(db, row, index)
            payload_hash = _payload_hash(normalized.normalized_payload)
        except ConnectorValidationError as exc:
            payload_hash = _payload_hash(row)
            existing = _find_source_submission(db, source_name=source_name, idempotency_key=external_id)
            if existing is not None:
                status, reason = _status_from_existing(existing, payload_hash)
                summary[f"{status}_count"] += 1
                results.append(
                    {
                        "external_id": external_id,
                        "status": status,
                        "submission_type": existing.submission_type,
                        "source_submission_id": existing.id,
                        "approval_workflow_id": None,
                        "reason": reason,
                    }
                )
                continue

            summary["rejected_count"] += 1
            if dry_run:
                results.append(
                    {
                        "external_id": external_id,
                        "status": "rejected",
                        "reason": str(exc),
                        "submission_type": None,
                        "source_submission_id": None,
                        "approval_workflow_id": None,
                    }
                )
                continue

            source_submission = SourceSubmission(
                submission_type="connector_untyped",
                source_name=source_name,
                source_channel=AGENCY_SOURCE_CHANNEL,
                client_id=connector_key,
                sync_batch_id=sync_batch_id,
                idempotency_key=external_id,
                payload_hash=payload_hash,
                submitted_by=actor_user_id,
                submitted_at=datetime.utcnow(),
                status="rejected",
                conflict_reason=str(exc),
                payload=row,
                provenance_json={
                    "connector_key": connector_key,
                    "source_name": source_name,
                    "adapter_version": adapter.definition.adapter_version,
                    "validation_errors": [str(exc)],
                    "correlation_id": correlation_id,
                },
                created_by=actor_user_id,
                updated_by=actor_user_id,
            )
            db.add(source_submission)
            db.flush()
            results.append(
                {
                    "external_id": external_id,
                    "status": "rejected",
                    "reason": str(exc),
                    "submission_type": source_submission.submission_type,
                    "source_submission_id": source_submission.id,
                    "approval_workflow_id": None,
                }
            )
            continue

        existing = _find_source_submission(db, source_name=source_name, idempotency_key=external_id)
        if existing is not None:
            status, reason = _status_from_existing(existing, payload_hash)
            summary[f"{status}_count"] += 1
            results.append(
                {
                    "external_id": external_id,
                    "status": status,
                    "submission_type": normalized.submission_type,
                    "source_submission_id": existing.id,
                    "approval_workflow_id": None,
                    "reason": reason,
                }
            )
            continue

        summary["accepted_count"] += 1
        summary["pending_approval_count"] += 1
        if dry_run:
            results.append(
                {
                    "external_id": external_id,
                    "status": "pending_approval",
                    "submission_type": normalized.submission_type,
                    "source_submission_id": None,
                    "approval_workflow_id": None,
                    "reason": None,
                }
            )
            continue

        source_submission = SourceSubmission(
            submission_type=normalized.submission_type,
            source_name=source_name,
            source_channel=AGENCY_SOURCE_CHANNEL,
            client_id=connector_key,
            sync_batch_id=sync_batch_id,
            idempotency_key=external_id,
            payload_hash=payload_hash,
            submitted_by=actor_user_id,
            submitted_at=datetime.utcnow(),
            status="pending_approval",
            payload=normalized.raw_payload,
            provenance_json={
                "connector_key": connector_key,
                "source_name": source_name,
                "adapter_version": adapter.definition.adapter_version,
                "normalized_payload": normalized.normalized_payload,
                "validation_errors": [],
                "correlation_id": correlation_id,
            },
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(source_submission)
        db.flush()

        workflow = ApprovalWorkflow(
            entity_type="source_submission",
            entity_id=str(source_submission.id),
            requested_by=actor_user_id,
            status="pending",
            notes=f"Connector ingestion pending review ({connector_key})",
            requested_at=datetime.utcnow(),
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(workflow)
        db.flush()

        provenance = dict(source_submission.provenance_json or {})
        provenance["approval_workflow_id"] = workflow.id
        source_submission.provenance_json = provenance
        source_submission.updated_by = actor_user_id
        db.flush()

        summary["workflow_created_count"] += 1
        results.append(
            {
                "external_id": external_id,
                "status": "pending_approval",
                "submission_type": normalized.submission_type,
                "source_submission_id": source_submission.id,
                "approval_workflow_id": workflow.id,
                "reason": None,
            }
        )

    return {**summary, "results": results}


def run_all_connector_ingestions(
    db: Session,
    *,
    actor_user_id: int | None,
    correlation_id: str | None,
    limit_per_connector: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    per_connector: list[dict[str, Any]] = []
    totals = {
        "fetched_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "duplicate_count": 0,
        "conflict_count": 0,
        "pending_approval_count": 0,
        "workflow_created_count": 0,
    }

    for connector_key in sorted(CONNECTOR_ADAPTERS.keys()):
        result = run_connector_ingestion(
            db,
            connector_key=connector_key,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            limit=limit_per_connector,
            dry_run=dry_run,
        )
        per_connector.append(result)
        for key in totals:
            totals[key] += int(result.get(key, 0))

    return {
        "connectors_run": len(per_connector),
        "dry_run": dry_run,
        "totals": totals,
        "results": per_connector,
    }


def list_connector_submissions(
    db: Session,
    *,
    connector_key: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = (
        select(SourceSubmission)
        .where(SourceSubmission.source_channel == AGENCY_SOURCE_CHANNEL)
        .order_by(SourceSubmission.id.desc())
        .limit(max(1, min(limit, 500)))
    )
    if connector_key:
        stmt = stmt.where(SourceSubmission.source_name == _build_source_name(connector_key))
    if status:
        stmt = stmt.where(SourceSubmission.status == status)

    submissions = list(db.scalars(stmt))
    if not submissions:
        return []

    entity_ids = [str(row.id) for row in submissions]
    workflows = list(
        db.scalars(
            select(ApprovalWorkflow)
            .where(
                ApprovalWorkflow.entity_type == "source_submission",
                ApprovalWorkflow.entity_id.in_(entity_ids),
            )
            .order_by(ApprovalWorkflow.id.desc())
        )
    )
    workflow_map: dict[str, ApprovalWorkflow] = {}
    for workflow in workflows:
        if workflow.entity_id not in workflow_map:
            workflow_map[workflow.entity_id] = workflow

    output: list[dict[str, Any]] = []
    for row in submissions:
        workflow = workflow_map.get(str(row.id))
        output.append(
            {
                "id": row.id,
                "connector_key": _connector_key_from_source(row.source_name),
                "source_name": row.source_name,
                "submission_type": row.submission_type,
                "status": row.status,
                "idempotency_key": row.idempotency_key,
                "target_entity_type": row.target_entity_type,
                "target_entity_id": row.target_entity_id,
                "conflict_reason": row.conflict_reason,
                "submitted_by": row.submitted_by,
                "submitted_at": row.submitted_at,
                "approval_workflow_id": workflow.id if workflow else None,
                "approval_status": workflow.status if workflow else None,
                "provenance": row.provenance_json,
            }
        )
    return output


def list_connector_approval_workflows(
    db: Session,
    *,
    connector_key: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    stmt = (
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.entity_type == "source_submission")
        .order_by(ApprovalWorkflow.requested_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    if status:
        stmt = stmt.where(ApprovalWorkflow.status == status)
    workflows = list(db.scalars(stmt))
    if not workflows:
        return []

    submission_ids = [int(row.entity_id) for row in workflows if row.entity_id.isdigit()]
    submission_rows = list(
        db.scalars(select(SourceSubmission).where(SourceSubmission.id.in_(submission_ids)))
    )
    submission_map = {row.id: row for row in submission_rows}

    output: list[dict[str, Any]] = []
    for workflow in workflows:
        if not workflow.entity_id.isdigit():
            continue
        submission_id = int(workflow.entity_id)
        source_submission = submission_map.get(submission_id)
        if source_submission is None:
            continue
        key = _connector_key_from_source(source_submission.source_name)
        if connector_key and key != connector_key:
            continue
        output.append(
            {
                "workflow_id": workflow.id,
                "status": workflow.status,
                "requested_by": workflow.requested_by,
                "reviewed_by": workflow.reviewed_by,
                "requested_at": workflow.requested_at,
                "reviewed_at": workflow.reviewed_at,
                "notes": workflow.notes,
                "source_submission_id": submission_id,
                "connector_key": key,
                "submission_type": source_submission.submission_type,
                "source_submission_status": source_submission.status,
                "source_submission_conflict_reason": source_submission.conflict_reason,
            }
        )
    return output


def _apply_farmgate_price_submission(db: Session, payload: dict[str, Any], actor_user_id: int | None) -> tuple[str, str]:
    data = PriceReportCreate(**payload)
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
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(row)
        db.flush()
        return "farmgate_price_report", str(row.id)

    existing.price_per_kg = data.price_per_kg
    existing.updated_by = actor_user_id
    db.flush()
    return "farmgate_price_report", str(existing.id)


def _apply_import_submission(db: Session, payload: dict[str, Any], actor_user_id: int | None) -> tuple[str, str]:
    data = ImportRecordCreate(**payload)
    existing = db.scalar(
        select(ImportRecord)
        .where(ImportRecord.import_reference == data.import_reference)
        .order_by(ImportRecord.id.desc())
        .limit(1)
    )
    if existing is None:
        row = ImportRecord(
            import_reference=data.import_reference,
            origin_country=data.origin_country,
            arrival_date=data.arrival_date,
            reporting_month=data.reporting_month,
            volume_tons=data.volume_tons,
            status=data.status,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(row)
        db.flush()
        return "import_record", str(row.id)

    existing.origin_country = data.origin_country
    existing.arrival_date = data.arrival_date
    existing.reporting_month = data.reporting_month
    existing.volume_tons = data.volume_tons
    existing.status = data.status
    existing.updated_by = actor_user_id
    db.flush()
    return "import_record", str(existing.id)


def _apply_warehouse_stock_submission(db: Session, payload: dict[str, Any], actor_user_id: int | None) -> tuple[str, str]:
    data = WarehouseStockReportCreate(**payload)
    existing = db.scalar(
        select(WarehouseStockReport)
        .where(
            WarehouseStockReport.warehouse_id == data.warehouse_id,
            WarehouseStockReport.report_date == data.report_date,
            WarehouseStockReport.reporting_month == data.reporting_month,
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
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(row)
        db.flush()
        return "warehouse_stock_report", str(row.id)

    existing.current_stock_tons = data.current_stock_tons
    existing.inflow_tons = data.inflow_tons
    existing.outflow_tons = data.outflow_tons
    existing.updated_by = actor_user_id
    db.flush()
    return "warehouse_stock_report", str(existing.id)


def _apply_approved_submission(
    db: Session,
    *,
    submission_type: str,
    normalized_payload: dict[str, Any],
    actor_user_id: int | None,
) -> tuple[str, str]:
    if submission_type == "farmgate_price_report":
        return _apply_farmgate_price_submission(db, normalized_payload, actor_user_id)
    if submission_type == "import_record":
        return _apply_import_submission(db, normalized_payload, actor_user_id)
    if submission_type == "warehouse_stock_report":
        return _apply_warehouse_stock_submission(db, normalized_payload, actor_user_id)
    raise ConnectorValidationError(f"Unsupported submission_type for approval: {submission_type}")


def review_connector_workflow(
    db: Session,
    *,
    workflow_id: int,
    action: str,
    reviewer_user_id: int | None,
    notes: str | None,
) -> dict[str, Any]:
    workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.id == workflow_id))
    if workflow is None:
        raise ConnectorValidationError("Approval workflow not found")
    if workflow.entity_type != "source_submission":
        raise ConnectorValidationError("Approval workflow is not linked to source submission")
    if workflow.status != "pending":
        raise ConnectorValidationError("Approval workflow is not pending")
    if not workflow.entity_id.isdigit():
        raise ConnectorValidationError("Invalid source submission reference in workflow")

    submission_id = int(workflow.entity_id)
    source_submission = db.scalar(select(SourceSubmission).where(SourceSubmission.id == submission_id))
    if source_submission is None:
        raise ConnectorValidationError("Source submission not found")

    action_normalized = action.strip().lower()
    reviewed_at = datetime.utcnow()

    if action_normalized == "reject":
        workflow.status = "rejected"
        workflow.reviewed_by = reviewer_user_id
        workflow.reviewed_at = reviewed_at
        workflow.notes = notes
        workflow.updated_by = reviewer_user_id

        source_submission.status = "rejected"
        source_submission.conflict_reason = "approval_rejected"
        source_submission.updated_by = reviewer_user_id
        db.flush()
        return {
            "workflow_id": workflow.id,
            "status": workflow.status,
            "source_submission_id": source_submission.id,
            "source_submission_status": source_submission.status,
            "target_entity_type": source_submission.target_entity_type,
            "target_entity_id": source_submission.target_entity_id,
            "reviewed_at": reviewed_at,
        }

    if action_normalized != "approve":
        raise ConnectorValidationError("Unsupported approval action")

    provenance = source_submission.provenance_json or {}
    normalized_payload = provenance.get("normalized_payload")
    if not isinstance(normalized_payload, dict):
        raise ConnectorValidationError("Missing normalized payload for source submission")

    target_entity_type, target_entity_id = _apply_approved_submission(
        db,
        submission_type=source_submission.submission_type,
        normalized_payload=normalized_payload,
        actor_user_id=reviewer_user_id,
    )

    workflow.status = "approved"
    workflow.reviewed_by = reviewer_user_id
    workflow.reviewed_at = reviewed_at
    workflow.notes = notes
    workflow.updated_by = reviewer_user_id

    source_submission.status = "approved"
    source_submission.target_entity_type = target_entity_type
    source_submission.target_entity_id = target_entity_id
    source_submission.conflict_reason = None
    source_submission.updated_by = reviewer_user_id

    next_provenance = dict(provenance)
    next_provenance["approval"] = {
        "status": "approved",
        "reviewed_by": reviewer_user_id,
        "reviewed_at": reviewed_at.isoformat(),
        "notes": notes,
    }
    source_submission.provenance_json = next_provenance
    db.flush()
    return {
        "workflow_id": workflow.id,
        "status": workflow.status,
        "source_submission_id": source_submission.id,
        "source_submission_status": source_submission.status,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "reviewed_at": reviewed_at,
    }
