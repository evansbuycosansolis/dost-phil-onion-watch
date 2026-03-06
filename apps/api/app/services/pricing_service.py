from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FarmgatePriceReport, RetailPriceReport, WholesalePriceReport


def list_farmgate_prices(db: Session, municipality_id: int | None = None) -> list[FarmgatePriceReport]:
    stmt = select(FarmgatePriceReport).order_by(FarmgatePriceReport.report_date.desc())
    if municipality_id:
        stmt = stmt.where(FarmgatePriceReport.municipality_id == municipality_id)
    return list(db.scalars(stmt))


def create_farmgate_price(db: Session, item: FarmgatePriceReport) -> FarmgatePriceReport:
    db.add(item)
    db.flush()
    return item


def create_wholesale_price(db: Session, item: WholesalePriceReport) -> WholesalePriceReport:
    db.add(item)
    db.flush()
    return item


def create_retail_price(db: Session, item: RetailPriceReport) -> RetailPriceReport:
    db.add(item)
    db.flush()
    return item
