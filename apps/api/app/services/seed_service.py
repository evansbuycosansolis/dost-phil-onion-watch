from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Barangay,
    ColdStorageFacility,
    ColdStorageStockReport,
    DemandEstimate,
    DistributionLog,
    FarmLocation,
    FarmerProfile,
    FarmgatePriceReport,
    HarvestReport,
    ImportRecord,
    Market,
    Municipality,
    PlantingRecord,
    Role,
    ShipmentArrival,
    StakeholderOrganization,
    StockReleaseLog,
    User,
    UserRole,
    Warehouse,
    WarehouseStockReport,
    WholesalePriceReport,
    RetailPriceReport,
    YieldEstimate,
    Document,
)
from app.services.document_ingestion_service import ingest_document

DEMO_PASSWORD = "ChangeMe123!"

ROLE_DEFINITIONS = [
    ("super_admin", "System super administrator"),
    ("provincial_admin", "Provincial operations administrator"),
    ("municipal_encoder", "Municipal encoder for submissions"),
    ("warehouse_operator", "Warehouse and cold storage operator"),
    ("market_analyst", "Market analytics reviewer"),
    ("policy_reviewer", "Policy and interventions reviewer"),
    ("executive_viewer", "Read-only executive dashboard viewer"),
    ("auditor", "Audit and compliance reviewer"),
]

MUNICIPALITIES = [
    ("OM-SJ", "San Jose"),
    ("OM-MB", "Mamburao"),
    ("OM-RIZ", "Rizal"),
    ("OM-SAB", "Sabalayan"),
    ("OM-CAL", "Calintaan"),
]


def _month_list(count: int = 12) -> list[date]:
    today = date.today().replace(day=1)
    months = []
    cursor = today
    for _ in range(count):
        months.append(cursor)
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    months.reverse()
    return months


def _ensure_role(db: Session, name: str, description: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role:
        return role
    role = Role(name=name, description=description)
    db.add(role)
    db.flush()
    return role


def _ensure_user(db: Session, email: str, full_name: str, municipality_id: int | None, role: Role) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        if not db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)):
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.flush()
        return user

    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(DEMO_PASSWORD),
        municipality_id=municipality_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    return user


def _ensure_seed_documents() -> list[tuple[str, str, str]]:
    docs_root = Path(__file__).resolve().parents[4] / "data" / "documents"
    docs_root.mkdir(parents=True, exist_ok=True)

    docs = [
        (
            "Occidental Mindoro Onion Supply Advisory 2025",
            "advisory_2025.md",
            "Policy bulletin discussing recommended stock release pacing and import timing windows.",
        ),
        (
            "Warehouse Inspection Highlights",
            "warehouse_inspection_highlights.md",
            "Inspection notes for storage utilization, stock handling controls, and release compliance.",
        ),
        (
            "Market Price Monitoring Protocol",
            "market_price_monitoring_protocol.md",
            "Guidance on farmgate, wholesale, and retail reporting cadence and verification.",
        ),
    ]

    output = []
    for title, filename, content in docs:
        path = docs_root / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        output.append((title, filename, str(path)))
    return output


def seed_reference_data(db: Session) -> dict:
    roles: dict[str, Role] = {}
    for name, description in ROLE_DEFINITIONS:
        roles[name] = _ensure_role(db, name, description)

    org = db.scalar(select(StakeholderOrganization).where(StakeholderOrganization.name == "Occidental Mindoro Provincial Agriculture Office"))
    if not org:
        org = StakeholderOrganization(name="Occidental Mindoro Provincial Agriculture Office", organization_type="government")
        db.add(org)
        db.flush()

    municipality_map: dict[str, Municipality] = {}
    for code, name in MUNICIPALITIES:
        municipality = db.scalar(select(Municipality).where(Municipality.code == code))
        if not municipality:
            municipality = Municipality(code=code, name=name)
            db.add(municipality)
            db.flush()
        municipality_map[code] = municipality

        if not db.scalar(select(Barangay).where(Barangay.municipality_id == municipality.id)):
            db.add_all(
                [
                    Barangay(municipality_id=municipality.id, name=f"Barangay {name} Norte"),
                    Barangay(municipality_id=municipality.id, name=f"Barangay {name} Sur"),
                ]
            )
            db.flush()

        if not db.scalar(select(Market).where(Market.municipality_id == municipality.id)):
            db.add(
                Market(municipality_id=municipality.id, name=f"{name} Public Market", market_type="public")
            )
            db.flush()

    # Demo users per role.
    _ensure_user(db, "super_admin@onionwatch.ph", "Super Admin", None, roles["super_admin"])
    _ensure_user(db, "provincial_admin@onionwatch.ph", "Provincial Admin", None, roles["provincial_admin"])
    _ensure_user(db, "municipal_encoder@onionwatch.ph", "Municipal Encoder", municipality_map["OM-SJ"].id, roles["municipal_encoder"])
    _ensure_user(db, "warehouse_operator@onionwatch.ph", "Warehouse Operator", municipality_map["OM-MB"].id, roles["warehouse_operator"])
    _ensure_user(db, "market_analyst@onionwatch.ph", "Market Analyst", None, roles["market_analyst"])
    _ensure_user(db, "policy_reviewer@onionwatch.ph", "Policy Reviewer", None, roles["policy_reviewer"])
    _ensure_user(db, "executive_viewer@onionwatch.ph", "Executive Viewer", None, roles["executive_viewer"])
    _ensure_user(db, "auditor@onionwatch.ph", "Auditor", None, roles["auditor"])

    return {
        "roles": len(roles),
        "municipalities": len(municipality_map),
    }


def seed_operational_data(db: Session) -> dict:
    months = _month_list(12)
    municipalities = db.scalars(select(Municipality).order_by(Municipality.id)).all()
    markets = {m.municipality_id: m for m in db.scalars(select(Market)).all()}

    # Warehouses and cold storage facilities.
    warehouse_by_muni: dict[int, Warehouse] = {}
    for municipality in municipalities:
        warehouse = db.scalar(select(Warehouse).where(Warehouse.municipality_id == municipality.id))
        if not warehouse:
            warehouse = Warehouse(
                municipality_id=municipality.id,
                name=f"{municipality.name} Onion Warehouse",
                location=f"{municipality.name}, Occidental Mindoro",
                capacity_tons=420 + municipality.id * 55,
            )
            db.add(warehouse)
            db.flush()
        warehouse_by_muni[municipality.id] = warehouse

        cold_storage = db.scalar(select(ColdStorageFacility).where(ColdStorageFacility.municipality_id == municipality.id))
        if not cold_storage:
            db.add(
                ColdStorageFacility(
                    warehouse_id=warehouse.id,
                    municipality_id=municipality.id,
                    name=f"{municipality.name} Cold Storage",
                    location=f"{municipality.name} Agro Hub",
                    capacity_tons=200 + municipality.id * 20,
                )
            )
            db.flush()

    # Farmers and farm locations.
    for municipality in municipalities:
        existing = db.scalar(select(FarmerProfile).where(FarmerProfile.municipality_id == municipality.id))
        if existing:
            continue
        barangay = db.scalar(select(Barangay).where(Barangay.municipality_id == municipality.id))
        for i in range(1, 4):
            farmer = FarmerProfile(
                farmer_code=f"{municipality.code}-F{i:02d}",
                full_name=f"{municipality.name} Farmer {i}",
                municipality_id=municipality.id,
                barangay_id=barangay.id if barangay else None,
                phone_number=f"+63-917-555-{municipality.id}{i:02d}",
            )
            db.add(farmer)
            db.flush()
            farm_location = FarmLocation(
                farmer_id=farmer.id,
                municipality_id=municipality.id,
                barangay_id=barangay.id if barangay else None,
                area_hectares=1.5 + i * 0.8,
                latitude=12.0 + municipality.id * 0.15,
                longitude=120.5 + i * 0.08,
            )
            db.add(farm_location)
            db.flush()
            db.add(
                PlantingRecord(
                    farmer_id=farmer.id,
                    farm_location_id=farm_location.id,
                    planting_date=months[0],
                    expected_harvest_month=months[min(5, len(months) - 1)],
                    variety="Red Creole",
                    area_hectares=farm_location.area_hectares,
                )
            )
        db.flush()

    # Monthly production, stock, release, pricing, demand.
    for month_index, month in enumerate(months):
        seasonal_wave = 1.0 + 0.28 * math.sin((month_index / 12) * 2 * math.pi)
        for municipality in municipalities:
            base = 190 + municipality.id * 18
            harvest_value = round(base * seasonal_wave, 2)

            # Harvest report per municipality per month.
            if not db.scalar(
                select(HarvestReport).where(HarvestReport.municipality_id == municipality.id, HarvestReport.reporting_month == month)
            ):
                db.add(
                    HarvestReport(
                        municipality_id=municipality.id,
                        reporting_month=month,
                        harvest_date=month,
                        volume_tons=harvest_value,
                        quality_grade="A",
                    )
                )

            if not db.scalar(
                select(YieldEstimate).where(YieldEstimate.municipality_id == municipality.id, YieldEstimate.reporting_month == month)
            ):
                db.add(
                    YieldEstimate(
                        municipality_id=municipality.id,
                        reporting_month=month,
                        estimated_yield_tons=round(harvest_value * 1.07, 2),
                        confidence=0.72,
                    )
                )

            warehouse = warehouse_by_muni[municipality.id]
            stock_value = round(harvest_value * (0.45 + 0.1 * math.cos(month_index)), 2)
            release_value = round(harvest_value * (0.3 + 0.05 * math.sin(month_index)), 2)

            if not db.scalar(
                select(WarehouseStockReport).where(
                    WarehouseStockReport.warehouse_id == warehouse.id,
                    WarehouseStockReport.reporting_month == month,
                )
            ):
                db.add(
                    WarehouseStockReport(
                        warehouse_id=warehouse.id,
                        municipality_id=municipality.id,
                        reporting_month=month,
                        report_date=month,
                        current_stock_tons=stock_value,
                        inflow_tons=round(harvest_value * 0.8, 2),
                        outflow_tons=release_value,
                    )
                )

            cold_storage = db.scalar(select(ColdStorageFacility).where(ColdStorageFacility.warehouse_id == warehouse.id))
            if cold_storage and not db.scalar(
                select(ColdStorageStockReport).where(
                    ColdStorageStockReport.cold_storage_facility_id == cold_storage.id,
                    ColdStorageStockReport.reporting_month == month,
                )
            ):
                utilization = round(min(95.0, max(35.0, (stock_value / cold_storage.capacity_tons) * 100)), 2)
                db.add(
                    ColdStorageStockReport(
                        cold_storage_facility_id=cold_storage.id,
                        municipality_id=municipality.id,
                        reporting_month=month,
                        report_date=month,
                        current_stock_tons=round(stock_value * 0.55, 2),
                        utilization_pct=utilization,
                    )
                )

            if not db.scalar(
                select(StockReleaseLog).where(StockReleaseLog.warehouse_id == warehouse.id, StockReleaseLog.reporting_month == month)
            ):
                db.add(
                    StockReleaseLog(
                        warehouse_id=warehouse.id,
                        release_date=month,
                        reporting_month=month,
                        volume_tons=release_value,
                        destination_market_id=markets[municipality.id].id if municipality.id in markets else None,
                        notes="Monthly staged release",
                    )
                )

            if not db.scalar(
                select(DistributionLog).where(
                    DistributionLog.municipality_id == municipality.id,
                    DistributionLog.reporting_month == month,
                )
            ):
                db.add(
                    DistributionLog(
                        municipality_id=municipality.id,
                        market_id=markets[municipality.id].id if municipality.id in markets else None,
                        distribution_date=month,
                        reporting_month=month,
                        volume_tons=round(release_value * 0.95, 2),
                    )
                )

            farmgate = round(44 + municipality.id * 1.2 + month_index * 0.3, 2)
            wholesale = round(farmgate + 9 + 0.6 * math.sin(month_index), 2)
            retail = round(wholesale + 11 + 0.9 * math.cos(month_index), 2)

            if not db.scalar(
                select(FarmgatePriceReport).where(
                    FarmgatePriceReport.municipality_id == municipality.id,
                    FarmgatePriceReport.reporting_month == month,
                )
            ):
                db.add(
                    FarmgatePriceReport(
                        municipality_id=municipality.id,
                        report_date=month,
                        reporting_month=month,
                        price_per_kg=farmgate,
                    )
                )

            if not db.scalar(
                select(WholesalePriceReport).where(
                    WholesalePriceReport.municipality_id == municipality.id,
                    WholesalePriceReport.reporting_month == month,
                )
            ):
                db.add(
                    WholesalePriceReport(
                        municipality_id=municipality.id,
                        market_id=markets[municipality.id].id if municipality.id in markets else None,
                        report_date=month,
                        reporting_month=month,
                        price_per_kg=wholesale,
                    )
                )

            if not db.scalar(
                select(RetailPriceReport).where(
                    RetailPriceReport.municipality_id == municipality.id,
                    RetailPriceReport.reporting_month == month,
                )
            ):
                db.add(
                    RetailPriceReport(
                        municipality_id=municipality.id,
                        market_id=markets[municipality.id].id if municipality.id in markets else None,
                        report_date=month,
                        reporting_month=month,
                        price_per_kg=retail,
                    )
                )

            if not db.scalar(
                select(DemandEstimate).where(DemandEstimate.municipality_id == municipality.id, DemandEstimate.reporting_month == month)
            ):
                db.add(
                    DemandEstimate(
                        municipality_id=municipality.id,
                        reporting_month=month,
                        demand_tons=round(base * 0.86, 2),
                        method="moving_average_baseline",
                    )
                )

        # Imports every few months.
        if month_index % 3 == 1:
            ref = f"IMP-{month.strftime('%Y%m')}-OM"
            if not db.scalar(select(ImportRecord).where(ImportRecord.import_reference == ref)):
                volume = round(220 + month_index * 18, 2)
                record = ImportRecord(
                    import_reference=ref,
                    origin_country="Netherlands" if month_index % 2 == 0 else "India",
                    arrival_date=month,
                    reporting_month=month,
                    volume_tons=volume,
                    status="arrived",
                )
                db.add(record)
                db.flush()
                db.add(
                    ShipmentArrival(
                        import_record_id=record.id,
                        port_name="Batangas Port",
                        arrival_date=month,
                        volume_tons=volume,
                        inspection_status="cleared",
                    )
                )

    # Add static seed document files.
    documents_seeded = _ensure_seed_documents()

    db.flush()
    return {
        "months_seeded": len(months),
        "municipalities": len(municipalities),
        "documents_files": len(documents_seeded),
    }


def seed_documents(db: Session, uploaded_by: int | None = None) -> dict:
    docs = _ensure_seed_documents()
    created = 0
    for title, file_name, file_path in docs:
        existing = db.scalar(select(Document).where(Document.file_name == file_name))
        if existing:
            continue
        ingest_document(
            db,
            title=title,
            file_name=file_name,
            file_path=file_path,
            source_type="seed_reference",
            uploaded_by=uploaded_by,
        )
        created += 1
    db.flush()
    return {"documents_indexed": created, "documents_available": len(docs)}
