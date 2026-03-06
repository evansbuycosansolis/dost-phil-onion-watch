from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HarvestReport, PlantingRecord


def list_harvest_reports(db: Session, municipality_id: int | None = None) -> list[HarvestReport]:
    stmt = select(HarvestReport).order_by(HarvestReport.harvest_date.desc())
    if municipality_id:
        stmt = stmt.where(HarvestReport.municipality_id == municipality_id)
    return list(db.scalars(stmt))


def create_harvest_report(db: Session, report: HarvestReport) -> HarvestReport:
    db.add(report)
    db.flush()
    return report


def list_planting_records(db: Session, municipality_id: int | None = None) -> list[PlantingRecord]:
    stmt = select(PlantingRecord).order_by(PlantingRecord.planting_date.desc())
    if municipality_id:
        stmt = stmt.where(PlantingRecord.farm_location_id == municipality_id)
    return list(db.scalars(stmt))
