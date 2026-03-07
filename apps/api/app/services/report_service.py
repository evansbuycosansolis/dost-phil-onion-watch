from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Municipality, ReportRecord, Warehouse, WarehouseStockReport
from app.services.forecasting_service import latest_model_diagnostics

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except Exception:  # pragma: no cover
    A4 = None
    canvas = None


def _ensure_reports_path() -> Path:
    path = Path(settings.reports_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report_filename(category: str, reporting_month: date) -> str:
    return f"{category}_{reporting_month.isoformat()}.md"


def _forecast_diagnostics_summary(db: Session) -> tuple[list[str], dict[str, object]]:
    diagnostics = latest_model_diagnostics(db)
    run_id = diagnostics.get("run_id")
    selected_model_counts = diagnostics.get("selected_model_counts", {})
    avg_scores = diagnostics.get("model_avg_score", {})
    avg_mae = diagnostics.get("model_avg_holdout_mae", {})
    municipalities = diagnostics.get("municipality_diagnostics", [])

    summary = {
        "run_id": run_id,
        "selected_model_counts": selected_model_counts,
        "model_avg_score": avg_scores,
        "model_avg_holdout_mae": avg_mae,
        "municipalities_covered": len(municipalities),
    }

    if run_id is None:
        return (["## Forecast Model Diagnostics", "- No forecast run available yet."], summary)

    top_municipalities = municipalities[:5]
    lines = [
        "## Forecast Model Diagnostics",
        f"- Forecast run id: {run_id}",
        f"- Selected model counts: {selected_model_counts}",
        f"- Average model score: {avg_scores}",
        f"- Average holdout MAE: {avg_mae}",
        "",
        "### Municipality Selection Snapshot",
    ]
    for row in top_municipalities:
        lines.append(
            f"- {row.get('municipality_name')}: {row.get('selected_model')} "
            f"(score={row.get('selected_score')}, fallback={row.get('fallback_order')})"
        )
    if not top_municipalities:
        lines.append("- No municipality diagnostics captured.")
    return lines, summary


def generate_report(db: Session, category: str, reporting_month: date, generated_by: int | None = None) -> ReportRecord:
    reports_path = _ensure_reports_path()
    filename = _report_filename(category, reporting_month)
    path = reports_path / filename
    diagnostics_lines, diagnostics_summary = _forecast_diagnostics_summary(db)

    if category == "provincial_exec_summary":
        alerts = db.scalars(select(Alert).where(Alert.status.in_(["open", "acknowledged"]))).all()
        content = "\n".join(
            [
                f"# Provincial Executive Summary ({reporting_month.isoformat()})",
                "",
                f"Active alerts: {len(alerts)}",
                "",
                "## Alerts",
                *[f"- [{a.severity}] {a.title} ({a.status})" for a in alerts],
                "",
                *diagnostics_lines,
            ]
        )
        title = f"Provincial Executive Summary - {reporting_month.strftime('%B %Y')}"
    elif category == "warehouse_utilization":
        warehouses = db.scalars(select(Warehouse)).all()
        lines = [f"# Warehouse Utilization Report ({reporting_month.isoformat()})", ""]
        for warehouse in warehouses:
            latest = db.scalar(
                select(WarehouseStockReport)
                .where(WarehouseStockReport.warehouse_id == warehouse.id)
                .order_by(WarehouseStockReport.report_date.desc())
                .limit(1)
            )
            stock = latest.current_stock_tons if latest else 0
            utilization = (stock / warehouse.capacity_tons * 100) if warehouse.capacity_tons else 0
            lines.append(f"- {warehouse.name}: {stock:.2f} tons ({utilization:.1f}% utilization)")
        content = "\n".join(lines)
        title = f"Warehouse Utilization Report - {reporting_month.strftime('%B %Y')}"
    elif category == "municipality_summary":
        municipalities = db.scalars(select(Municipality)).all()
        content = "\n".join(
            [
                f"# Municipality Summary ({reporting_month.isoformat()})",
                "",
                "## Included Municipalities",
                *[f"- {m.name}" for m in municipalities],
                "",
                *diagnostics_lines,
            ]
        )
        title = f"Municipality Summary - {reporting_month.strftime('%B %Y')}"
    elif category == "price_trend":
        title = f"Price Trend Report - {reporting_month.strftime('%B %Y')}"
        content = "\n".join([f"# {title}", "", "Price trend analytics are generated from market reports.", "", *diagnostics_lines])
    elif category == "alert_digest":
        alerts = db.scalars(select(Alert).order_by(Alert.opened_at.desc()).limit(50)).all()
        title = f"Alert Digest - {reporting_month.strftime('%B %Y')}"
        content = "\n".join(
            [
                f"# {title}",
                "",
                "## Recent Alerts",
                *[f"- {a.title} | {a.alert_type} | {a.severity} | {a.status}" for a in alerts],
                "",
                *diagnostics_lines,
            ]
        )
    else:
        title = f"Generated Report - {reporting_month.isoformat()}"
        content = f"# {title}\n\nUnsupported category fallback content."

    path.write_text(content, encoding="utf-8")

    record = ReportRecord(
        category=category,
        title=title,
        reporting_month=reporting_month,
        file_path=str(path),
        status="generated",
        generated_by=generated_by,
        metadata_json={
            "generated_at": datetime.utcnow().isoformat(),
            "forecast_model_diagnostics": diagnostics_summary,
        },
    )
    db.add(record)
    db.flush()
    return record


def list_reports(db: Session, limit: int = 100) -> list[ReportRecord]:
    return list(db.scalars(select(ReportRecord).order_by(ReportRecord.generated_at.desc()).limit(limit)))


def get_report(db: Session, report_id: int) -> ReportRecord | None:
    return db.scalar(select(ReportRecord).where(ReportRecord.id == report_id))


def _ensure_export_dir() -> Path:
    export_dir = _ensure_reports_path() / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def _read_report_content(report: ReportRecord) -> str:
    if not report.file_path:
        return ""
    path = Path(report.file_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_csv_export(report: ReportRecord) -> Path:
    content = _read_report_content(report)
    export_path = _ensure_export_dir() / f"report_{report.id}_{report.reporting_month.isoformat()}.csv"

    rows: list[list[str]] = [["line_type", "segment_1", "segment_2", "segment_3", "raw"]]
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            rows.append(["heading", line.lstrip("#").strip(), "", "", line])
            continue
        if line.startswith("-"):
            parts = [part.strip() for part in line.lstrip("-").split("|")]
            while len(parts) < 3:
                parts.append("")
            rows.append(["bullet", parts[0], parts[1], parts[2], line])
            continue
        rows.append(["text", line, "", "", line])

    with export_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerows(rows)
    return export_path


def _build_pdf_export(report: ReportRecord) -> Path:
    content = _read_report_content(report)
    export_path = _ensure_export_dir() / f"report_{report.id}_{report.reporting_month.isoformat()}.pdf"

    if canvas is None or A4 is None:
        export_path.write_text(content, encoding="utf-8")
        return export_path

    pdf = canvas.Canvas(str(export_path), pagesize=A4)
    width, height = A4
    margin = 36
    y = height - margin
    line_height = 14

    for line in content.splitlines():
        normalized = (line or " ").strip()
        if y <= margin:
            pdf.showPage()
            y = height - margin
        pdf.drawString(margin, y, normalized[:120])
        y -= line_height

    pdf.save()
    return export_path


def export_report(report: ReportRecord, export_format: str) -> tuple[Path, str]:
    normalized = export_format.lower()
    if normalized == "csv":
        return _build_csv_export(report), "text/csv"
    if normalized == "pdf":
        return _build_pdf_export(report), "application/pdf"
    raise ValueError(f"Unsupported export format: {export_format}")
