from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportRecord, ShipmentArrival


def list_import_records(db: Session) -> list[ImportRecord]:
    return list(db.scalars(select(ImportRecord).order_by(ImportRecord.arrival_date.desc())))


def create_import_record(db: Session, record: ImportRecord) -> ImportRecord:
    db.add(record)
    db.flush()
    return record


def list_shipments(db: Session) -> list[ShipmentArrival]:
    return list(db.scalars(select(ShipmentArrival).order_by(ShipmentArrival.arrival_date.desc())))
