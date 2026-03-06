from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Warehouse, WarehouseStockReport


def list_warehouses(db: Session, municipality_id: int | None = None) -> list[Warehouse]:
    stmt = select(Warehouse).order_by(Warehouse.name)
    if municipality_id:
        stmt = stmt.where(Warehouse.municipality_id == municipality_id)
    return list(db.scalars(stmt))


def create_warehouse(db: Session, warehouse: Warehouse) -> Warehouse:
    db.add(warehouse)
    db.flush()
    return warehouse


def list_warehouse_stock_reports(db: Session, warehouse_id: int | None = None) -> list[WarehouseStockReport]:
    stmt = select(WarehouseStockReport).order_by(WarehouseStockReport.report_date.desc())
    if warehouse_id:
        stmt = stmt.where(WarehouseStockReport.warehouse_id == warehouse_id)
    return list(db.scalars(stmt))


def create_warehouse_stock_report(db: Session, record: WarehouseStockReport) -> WarehouseStockReport:
    db.add(record)
    db.flush()
    return record
