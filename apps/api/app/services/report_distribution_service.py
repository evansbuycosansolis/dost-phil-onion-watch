from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ReportDeliveryLog, ReportRecipientGroup, ReportRecord, Role, StakeholderOrganization, User, UserRole
from app.services.audit_service import emit_audit_event
from app.services.notification_service import notify_report_delivery_failure
from app.services.report_service import export_report

VALID_EXPORT_FORMATS = {"pdf", "csv"}
VALID_DELIVERY_CHANNELS = {"file_drop", "webhook"}


def _normalize_export_format(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in VALID_EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {value}")
    return normalized


def _normalize_delivery_channel(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in VALID_DELIVERY_CHANNELS:
        raise ValueError(f"Unsupported delivery channel: {value}")
    return normalized


def _safe_target(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def ensure_default_report_recipient_groups(db: Session, organization_id: int | None = None) -> dict[str, int]:
    defaults = [
        {
            "name": "Executives Provincial Summary",
            "description": "Provincial executive summary for executive viewers",
            "report_category": "provincial_exec_summary",
            "role_name": "executive_viewer",
            "organization_id": None,
            "export_format": "pdf",
        },
        {
            "name": "Provincial Admin Reports",
            "description": "All generated reports for provincial admins",
            "report_category": None,
            "role_name": "provincial_admin",
            "organization_id": organization_id,
            "export_format": "pdf",
        },
        {
            "name": "Policy Review Digest",
            "description": "Alert digest and municipality summary for policy reviewers",
            "report_category": "alert_digest",
            "role_name": "policy_reviewer",
            "organization_id": None,
            "export_format": "pdf",
        },
        {
            "name": "Analyst Data Pack",
            "description": "Price trend report for market analysts in CSV",
            "report_category": "price_trend",
            "role_name": "market_analyst",
            "organization_id": None,
            "export_format": "csv",
        },
        {
            "name": "Auditor Monthly Pack",
            "description": "Municipality summary for auditors",
            "report_category": "municipality_summary",
            "role_name": "auditor",
            "organization_id": None,
            "export_format": "pdf",
        },
    ]

    created = 0
    existing = 0
    for row in defaults:
        current = db.scalar(select(ReportRecipientGroup).where(ReportRecipientGroup.name == row["name"]))
        if current:
            existing += 1
            continue

        group = ReportRecipientGroup(
            name=row["name"],
            description=row["description"],
            report_category=row["report_category"],
            role_name=row["role_name"],
            organization_id=row["organization_id"],
            delivery_channel="file_drop",
            export_format=row["export_format"],
            max_attempts=settings.report_distribution_default_max_attempts,
            retry_backoff_seconds=settings.report_distribution_retry_backoff_seconds,
            notify_on_failure=True,
            is_active=True,
        )
        db.add(group)
        created += 1

    db.flush()
    return {"created": created, "existing": existing, "total_defaults": len(defaults)}


def list_recipient_groups(db: Session, active_only: bool = False) -> list[ReportRecipientGroup]:
    stmt = select(ReportRecipientGroup).order_by(ReportRecipientGroup.id.asc())
    if active_only:
        stmt = stmt.where(ReportRecipientGroup.is_active.is_(True))
    return list(db.scalars(stmt))


def get_recipient_group(db: Session, group_id: int) -> ReportRecipientGroup | None:
    return db.scalar(select(ReportRecipientGroup).where(ReportRecipientGroup.id == group_id))


def create_recipient_group(
    db: Session,
    *,
    name: str,
    description: str | None,
    report_category: str | None,
    role_name: str | None,
    organization_id: int | None,
    delivery_channel: str,
    export_format: str,
    max_attempts: int,
    retry_backoff_seconds: int,
    notify_on_failure: bool,
    is_active: bool,
    metadata: dict[str, object] | None,
    actor_user_id: int | None = None,
) -> ReportRecipientGroup:
    normalized_channel = _normalize_delivery_channel(delivery_channel)
    normalized_format = _normalize_export_format(export_format)
    validated_attempts = max(1, int(max_attempts))
    validated_backoff = max(5, int(retry_backoff_seconds))

    if role_name:
        role_exists = db.scalar(select(Role.id).where(Role.name == role_name))
        if role_exists is None:
            raise ValueError(f"Unknown role_name: {role_name}")
    if organization_id is not None:
        org_exists = db.scalar(select(StakeholderOrganization.id).where(StakeholderOrganization.id == organization_id))
        if org_exists is None:
            raise ValueError(f"Unknown organization_id: {organization_id}")

    group = ReportRecipientGroup(
        name=name,
        description=description,
        report_category=report_category,
        role_name=role_name,
        organization_id=organization_id,
        delivery_channel=normalized_channel,
        export_format=normalized_format,
        max_attempts=validated_attempts,
        retry_backoff_seconds=validated_backoff,
        notify_on_failure=notify_on_failure,
        is_active=is_active,
        metadata_json=metadata,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(group)
    db.flush()
    return group


def update_recipient_group(
    db: Session,
    *,
    group: ReportRecipientGroup,
    changes: dict[str, Any],
    actor_user_id: int | None = None,
) -> ReportRecipientGroup:
    nullable_fields = {"description", "report_category", "role_name", "organization_id", "metadata"}

    if "delivery_channel" in changes and changes["delivery_channel"] is not None:
        changes["delivery_channel"] = _normalize_delivery_channel(str(changes["delivery_channel"]))
    if "export_format" in changes and changes["export_format"] is not None:
        changes["export_format"] = _normalize_export_format(str(changes["export_format"]))
    if "max_attempts" in changes and changes["max_attempts"] is not None:
        changes["max_attempts"] = max(1, int(changes["max_attempts"]))
    if "retry_backoff_seconds" in changes and changes["retry_backoff_seconds"] is not None:
        changes["retry_backoff_seconds"] = max(5, int(changes["retry_backoff_seconds"]))
    if "role_name" in changes and changes["role_name"]:
        role_exists = db.scalar(select(Role.id).where(Role.name == str(changes["role_name"])))
        if role_exists is None:
            raise ValueError(f"Unknown role_name: {changes['role_name']}")
    if "organization_id" in changes and changes["organization_id"] is not None:
        org_exists = db.scalar(select(StakeholderOrganization.id).where(StakeholderOrganization.id == int(changes["organization_id"])))
        if org_exists is None:
            raise ValueError(f"Unknown organization_id: {changes['organization_id']}")

    for key, value in changes.items():
        if value is None and key not in nullable_fields:
            continue
        if key == "metadata":
            group.metadata_json = value
            continue
        setattr(group, key, value)
    group.updated_by = actor_user_id
    db.flush()
    return group


def _resolve_group_recipients(db: Session, group: ReportRecipientGroup) -> list[tuple[int, str, int | None]]:
    stmt = select(User.id, User.email, User.organization_id).where(User.is_active.is_(True))

    if group.organization_id is not None:
        stmt = stmt.where(User.organization_id == group.organization_id)

    if group.role_name:
        stmt = (
            stmt.join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.name == group.role_name)
        )

    rows = db.execute(stmt.distinct()).all()
    return [(int(uid), str(email), org_id if org_id is None else int(org_id)) for uid, email, org_id in rows]


def queue_report_distribution(
    db: Session,
    *,
    report: ReportRecord,
    actor_user_id: int | None = None,
    correlation_id: str | None = None,
) -> dict[str, int]:
    groups = list(
        db.scalars(
            select(ReportRecipientGroup).where(
                ReportRecipientGroup.is_active.is_(True),
                or_(ReportRecipientGroup.report_category.is_(None), ReportRecipientGroup.report_category == report.category),
            )
        )
    )

    queued = 0
    skipped = 0
    now = datetime.utcnow()

    for group in groups:
        recipients = _resolve_group_recipients(db, group)
        for user_id, email, organization_id in recipients:
            duplicate = db.scalar(
                select(ReportDeliveryLog.id).where(
                    ReportDeliveryLog.report_id == report.id,
                    ReportDeliveryLog.recipient_group_id == group.id,
                    ReportDeliveryLog.recipient_user_id == user_id,
                    ReportDeliveryLog.export_format == group.export_format,
                )
            )
            if duplicate:
                skipped += 1
                continue

            entry = ReportDeliveryLog(
                report_id=report.id,
                recipient_group_id=group.id,
                recipient_user_id=user_id,
                recipient_email=email,
                recipient_role=group.role_name,
                recipient_organization_id=organization_id,
                delivery_channel=group.delivery_channel,
                export_format=group.export_format,
                status="queued",
                attempt_count=0,
                max_attempts=max(1, group.max_attempts),
                next_attempt_at=now,
                payload_json={"group_name": group.name},
                created_by=actor_user_id,
                updated_by=actor_user_id,
            )
            db.add(entry)
            queued += 1

        if recipients:
            group.last_used_at = now

    db.flush()

    emit_audit_event(
        db,
        actor_user_id=actor_user_id,
        action_type="report.distribution.queued",
        entity_type="report_record",
        entity_id=str(report.id),
        after_payload={"queued_count": queued, "skipped_count": skipped, "group_count": len(groups)},
        correlation_id=correlation_id,
    )
    return {"report_id": report.id, "queued_count": queued, "skipped_count": skipped, "group_count": len(groups)}


def queue_undistributed_reports(
    db: Session,
    *,
    limit: int = 25,
    actor_user_id: int | None = None,
) -> dict[str, int]:
    reports = list(
        db.scalars(
            select(ReportRecord)
            .where(ReportRecord.status == "generated")
            .order_by(ReportRecord.generated_at.desc())
            .limit(max(1, min(limit, 500)))
        )
    )

    queued_reports = 0
    queued_deliveries = 0
    skipped_reports = 0
    for report in reports:
        has_existing = db.scalar(select(ReportDeliveryLog.id).where(ReportDeliveryLog.report_id == report.id).limit(1))
        if has_existing:
            skipped_reports += 1
            continue
        result = queue_report_distribution(db, report=report, actor_user_id=actor_user_id)
        queued_reports += 1
        queued_deliveries += result["queued_count"]

    return {
        "reports_scanned": len(reports),
        "queued_reports": queued_reports,
        "queued_deliveries": queued_deliveries,
        "skipped_reports": skipped_reports,
    }


def list_report_delivery_logs(
    db: Session,
    *,
    report_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[ReportDeliveryLog]:
    stmt = select(ReportDeliveryLog)
    if report_id is not None:
        stmt = stmt.where(ReportDeliveryLog.report_id == report_id)
    if status:
        stmt = stmt.where(ReportDeliveryLog.status == status)
    stmt = stmt.order_by(ReportDeliveryLog.id.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(stmt))


def _deliver_file_drop(*, report: ReportRecord, delivery: ReportDeliveryLog, export_path: Path, media_type: str) -> dict[str, Any]:
    base_dir = Path(settings.reports_path) / "deliveries" / _safe_target(delivery.recipient_email)
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / f"report_{report.id}_{report.reporting_month.isoformat()}.{delivery.export_format}"
    shutil.copyfile(export_path, target)
    return {
        "channel": "file_drop",
        "delivery_path": str(target),
        "source_export_path": str(export_path),
        "media_type": media_type,
    }


def _deliver_webhook(*, report: ReportRecord, delivery: ReportDeliveryLog, export_path: Path, media_type: str) -> dict[str, Any]:
    webhook_url = settings.report_distribution_webhook_url or settings.notification_webhook_url
    if not webhook_url:
        raise RuntimeError("REPORT_DISTRIBUTION_WEBHOOK_URL is not configured")

    payload = {
        "event": "report_distributed",
        "report": {
            "id": report.id,
            "category": report.category,
            "title": report.title,
            "reporting_month": report.reporting_month.isoformat(),
            "export_format": delivery.export_format,
            "media_type": media_type,
            "file_name": export_path.name,
            "file_path": str(export_path),
        },
        "recipient": {
            "user_id": delivery.recipient_user_id,
            "email": delivery.recipient_email,
            "role": delivery.recipient_role,
            "organization_id": delivery.recipient_organization_id,
        },
        "delivery_log_id": delivery.id,
        "attempt": delivery.attempt_count,
        "timestamp": datetime.utcnow().isoformat(),
    }

    response = httpx.post(webhook_url, json=payload, timeout=10.0)
    response.raise_for_status()
    return {
        "channel": "webhook",
        "webhook_url": webhook_url,
        "response_status": response.status_code,
        "response_text": response.text[:250],
        "source_export_path": str(export_path),
    }


def _dispatch_delivery(*, report: ReportRecord, delivery: ReportDeliveryLog, export_path: Path, media_type: str) -> dict[str, Any]:
    if delivery.delivery_channel == "file_drop":
        return _deliver_file_drop(report=report, delivery=delivery, export_path=export_path, media_type=media_type)
    if delivery.delivery_channel == "webhook":
        return _deliver_webhook(report=report, delivery=delivery, export_path=export_path, media_type=media_type)
    raise RuntimeError(f"Unsupported delivery channel: {delivery.delivery_channel}")


def process_pending_report_deliveries(
    db: Session,
    *,
    limit: int | None = None,
    actor_user_id: int | None = None,
) -> list[ReportDeliveryLog]:
    now = datetime.utcnow()
    batch_limit = max(1, min(int(limit or settings.report_distribution_batch_size), 500))

    deliveries = list(
        db.scalars(
            select(ReportDeliveryLog).where(
                ReportDeliveryLog.status.in_(["queued", "retrying"]),
                or_(ReportDeliveryLog.next_attempt_at.is_(None), ReportDeliveryLog.next_attempt_at <= now),
            )
            .order_by(ReportDeliveryLog.id.asc())
            .limit(batch_limit)
        )
    )

    for delivery in deliveries:
        previous_status = delivery.status
        report = db.scalar(select(ReportRecord).where(ReportRecord.id == delivery.report_id))
        group = db.scalar(select(ReportRecipientGroup).where(ReportRecipientGroup.id == delivery.recipient_group_id))

        if report is None or group is None:
            delivery.status = "failed"
            delivery.attempt_count += 1
            delivery.last_error = "Missing report or recipient group"
            delivery.next_attempt_at = None
            delivery.updated_by = actor_user_id
            continue

        delivery.status = "delivering"
        delivery.attempt_count += 1
        delivery.next_attempt_at = None
        delivery.last_error = None
        delivery.updated_by = actor_user_id
        db.flush()

        try:
            export_path, media_type = export_report(report, delivery.export_format)
            payload = _dispatch_delivery(report=report, delivery=delivery, export_path=export_path, media_type=media_type)

            delivery.status = "sent"
            delivery.delivered_at = datetime.utcnow()
            delivery.payload_json = payload
            delivery.last_error = None
            delivery.updated_by = actor_user_id

            emit_audit_event(
                db,
                actor_user_id=actor_user_id,
                action_type="report.distribution.sent",
                entity_type="report_delivery_log",
                entity_id=str(delivery.id),
                before_payload={"status": previous_status},
                after_payload={"status": delivery.status, "payload": payload},
            )
        except Exception as exc:
            error_text = str(exc)
            delivery.last_error = error_text
            if delivery.attempt_count >= max(1, delivery.max_attempts):
                delivery.status = "failed"
                delivery.next_attempt_at = None
                if group.notify_on_failure and delivery.notification_sent_at is None:
                    notify_report_delivery_failure(
                        report_id=delivery.report_id,
                        delivery_log_id=delivery.id,
                        recipient_email=delivery.recipient_email,
                        attempt=delivery.attempt_count,
                        max_attempts=delivery.max_attempts,
                        error_message=error_text,
                        context={
                            "delivery_channel": delivery.delivery_channel,
                            "export_format": delivery.export_format,
                            "recipient_group_id": delivery.recipient_group_id,
                        },
                    )
                    delivery.notification_sent_at = datetime.utcnow()

                emit_audit_event(
                    db,
                    actor_user_id=actor_user_id,
                    action_type="report.distribution.failed",
                    entity_type="report_delivery_log",
                    entity_id=str(delivery.id),
                    before_payload={"status": previous_status},
                    after_payload={"status": delivery.status, "error": error_text},
                )
            else:
                backoff = max(5, group.retry_backoff_seconds) * (2 ** max(0, delivery.attempt_count - 1))
                delivery.status = "retrying"
                delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=backoff)
                emit_audit_event(
                    db,
                    actor_user_id=actor_user_id,
                    action_type="report.distribution.retry_scheduled",
                    entity_type="report_delivery_log",
                    entity_id=str(delivery.id),
                    before_payload={"status": previous_status},
                    after_payload={
                        "status": delivery.status,
                        "error": error_text,
                        "next_attempt_at": delivery.next_attempt_at.isoformat(),
                    },
                )

            delivery.updated_by = actor_user_id

    db.flush()
    return deliveries


def distribution_status_summary(db: Session) -> dict[str, int]:
    statuses = ["queued", "retrying", "sent", "failed", "delivering"]
    summary: dict[str, int] = {}
    for status in statuses:
        count = db.scalar(select(func.count(ReportDeliveryLog.id)).where(ReportDeliveryLog.status == status))
        summary[status] = int(count or 0)
    return summary
