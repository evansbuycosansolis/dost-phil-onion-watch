from __future__ import annotations

import math
from datetime import date, datetime, timedelta
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
from app.services.anomaly_service import ensure_default_threshold_configs
from app.services.document_ingestion_service import ingest_document
from app.services.report_distribution_service import ensure_default_report_recipient_groups

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


def _ensure_demo_geospatial_aoi(db: Session) -> None:
    from datetime import datetime

    from app.models import GeospatialAOI, GeospatialAOIMetadata, GeospatialAOIVersion, Municipality
    from app.services.stac_service import geojson_to_bbox

    code = "OM-SJ-DEMO-AOI"
    existing = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == code))
    if existing is not None:
        meta = db.scalar(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id == existing.id))
        if meta is None:
            db.add(
                GeospatialAOIMetadata(
                    aoi_id=existing.id,
                    owner_user_id=None,
                    tags_json=["demo", "seed", "san-jose"],
                    labels_json=["pilot", "active-monitoring"],
                    watchlist_flag=True,
                    public_share_token="demo-public-token",
                    metadata_json={"watch_reason": "Seeded monitoring scope"},
                )
            )
            db.flush()
        return

    muni = db.scalar(select(Municipality).where(Municipality.code == "OM-SJ"))
    municipality_id = muni.id if muni else None

    boundary = {
        "type": "Polygon",
        "coordinates": [
            [
                [121.00, 12.20],
                [121.10, 12.20],
                [121.10, 12.30],
                [121.00, 12.30],
                [121.00, 12.20],
            ]
        ],
    }
    minx, miny, maxx, maxy = geojson_to_bbox(boundary)

    aoi = GeospatialAOI(
        code=code,
        name="San Jose Demo Onion AOI",
        description="Seeded AOI for local/dev STAC discovery smoke testing.",
        scope_type="municipality",
        municipality_id=municipality_id,
        warehouse_id=None,
        market_id=None,
        srid=4326,
        boundary_geojson=boundary,
        boundary_wkt=None,
        bbox_min_lng=float(minx),
        bbox_min_lat=float(miny),
        bbox_max_lng=float(maxx),
        bbox_max_lat=float(maxy),
        centroid_lng=float((minx + maxx) / 2.0),
        centroid_lat=float((miny + maxy) / 2.0),
        source="seed",
        is_active=True,
    )
    db.add(aoi)
    db.flush()

    db.add(
        GeospatialAOIVersion(
            aoi_id=aoi.id,
            version=1,
            change_type="create",
            boundary_geojson=aoi.boundary_geojson,
            boundary_wkt=aoi.boundary_wkt,
            changed_by=None,
            change_reason="seed",
            changed_at=datetime.utcnow(),
        )
    )
    db.add(
        GeospatialAOIMetadata(
            aoi_id=aoi.id,
            owner_user_id=None,
            tags_json=["demo", "seed", "san-jose"],
            labels_json=["pilot", "active-monitoring"],
            watchlist_flag=True,
            public_share_token="demo-public-token",
            metadata_json={"watch_reason": "Seeded monitoring scope"},
        )
    )
    db.flush()


def _ensure_demo_geospatial_features(db: Session) -> None:
    from app.models import GeospatialAOI, GeospatialFeature

    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == "OM-SJ-DEMO-AOI"))
    if aoi is None:
        return

    existing = db.scalar(select(GeospatialFeature).where(GeospatialFeature.aoi_id == aoi.id).limit(1))
    if existing is not None:
        return

    base_date = date.today()
    samples = [
        {
            "days_ago": 12,
            "source": "sentinel-2",
            "cloud_score": 0.18,
            "change_score": 0.24,
            "vegetation_vigor_score": 0.78,
            "crop_activity_score": 0.81,
            "observation_confidence_score": 0.86,
            "ndvi_mean": 0.69,
            "evi_mean": 0.45,
            "ndwi_mean": 0.21,
            "features_json": {"radar_change": False, "provider": "earth-search"},
            "quality_json": {"coverage": "good", "cloud_band_penalty": 0.18},
        },
        {
            "days_ago": 7,
            "source": "sentinel-1",
            "cloud_score": None,
            "change_score": 0.41,
            "vegetation_vigor_score": 0.72,
            "crop_activity_score": 0.76,
            "observation_confidence_score": 0.74,
            "ndvi_mean": None,
            "evi_mean": None,
            "ndwi_mean": None,
            "radar_backscatter_vv": -10.4,
            "radar_backscatter_vh": -16.2,
            "features_json": {"radar_change": True, "provider": "earth-search"},
            "quality_json": {"coverage": "good", "sar_continuity": True},
        },
        {
            "days_ago": 3,
            "source": "sentinel-2",
            "cloud_score": 0.09,
            "change_score": 0.18,
            "vegetation_vigor_score": 0.83,
            "crop_activity_score": 0.88,
            "observation_confidence_score": 0.92,
            "ndvi_mean": 0.74,
            "evi_mean": 0.49,
            "ndwi_mean": 0.24,
            "features_json": {"radar_change": False, "provider": "earth-search"},
            "quality_json": {"coverage": "excellent", "cloud_band_penalty": 0.09},
        },
    ]

    for sample in samples:
        observation_date = base_date - timedelta(days=sample["days_ago"])
        db.add(
            GeospatialFeature(
                aoi_id=aoi.id,
                source=str(sample["source"]),
                observation_date=observation_date,
                reporting_month=observation_date.replace(day=1),
                cloud_score=sample.get("cloud_score"),
                ndvi_mean=sample.get("ndvi_mean"),
                evi_mean=sample.get("evi_mean"),
                ndwi_mean=sample.get("ndwi_mean"),
                radar_backscatter_vv=sample.get("radar_backscatter_vv"),
                radar_backscatter_vh=sample.get("radar_backscatter_vh"),
                change_score=sample.get("change_score"),
                vegetation_vigor_score=sample.get("vegetation_vigor_score"),
                crop_activity_score=sample.get("crop_activity_score"),
                observation_confidence_score=sample.get("observation_confidence_score"),
                processing_run_id=None,
                features_json=sample.get("features_json") or {},
                quality_json=sample.get("quality_json") or {},
            )
        )
    db.flush()


def _ensure_demo_geospatial_runs(db: Session) -> None:
    from app.models import GeospatialAOI, SatellitePipelineRun

    existing = db.scalar(select(SatellitePipelineRun.id).limit(1))
    if existing is not None:
        return

    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == "OM-SJ-DEMO-AOI"))
    aoi_id = aoi.id if aoi else None
    now = datetime.utcnow()

    db.add_all(
        [
            SatellitePipelineRun(
                run_type="ingest",
                backend="earth-search",
                status="completed",
                started_at=now - timedelta(hours=8),
                finished_at=now - timedelta(hours=7, minutes=53),
                triggered_by=None,
                correlation_id="seed-geospatial-ingest-001",
                aoi_id=None,
                sources_json={"sources": ["sentinel-2", "sentinel-1"]},
                parameters_json={"lookback_days": 30},
                results_json={"aois_scanned": 1, "scenes_discovered": 6, "scenes_inserted": 6},
                notes="Seeded completed ingest run",
            ),
            SatellitePipelineRun(
                run_type="feature_refresh",
                backend="earth-search",
                status="completed",
                started_at=now - timedelta(hours=6),
                finished_at=now - timedelta(hours=5, minutes=58),
                triggered_by=None,
                correlation_id="seed-geospatial-refresh-001",
                aoi_id=aoi_id,
                sources_json={"sources": ["sentinel-2", "sentinel-1"]},
                parameters_json={"lookback_days": 30},
                results_json={"aois_scanned": 1, "scenes_scanned": 6, "features_inserted": 3, "features_updated": 0},
                notes="Seeded completed feature refresh run",
            ),
        ]
    )
    db.flush()


def _ensure_demo_geospatial_collaboration(db: Session) -> None:
    from app.models import (
        Document,
        GeospatialAOI,
        GeospatialAOIAttachment,
        GeospatialAOIDocumentLink,
        GeospatialAOIFavorite,
        GeospatialAOIMetadata,
        GeospatialAOINote,
        GeospatialFilterPreset,
        GeospatialRunEvent,
        GeospatialRunPreset,
        GeospatialRunSchedule,
        SatellitePipelineRun,
        User,
    )

    aoi = db.scalar(select(GeospatialAOI).where(GeospatialAOI.code == "OM-SJ-DEMO-AOI"))
    if aoi is None:
        return
    super_admin = db.scalar(select(User).where(User.email == "super_admin@onionwatch.ph"))
    if super_admin is None:
        return

    metadata = db.scalar(select(GeospatialAOIMetadata).where(GeospatialAOIMetadata.aoi_id == aoi.id))
    if metadata is not None:
        metadata.owner_user_id = super_admin.id
        metadata.tags_json = list(dict.fromkeys([*(metadata.tags_json or []), "priority-zone"]))
        metadata.labels_json = list(dict.fromkeys([*(metadata.labels_json or []), "field-verified"]))
        metadata.watchlist_flag = True
        metadata.metadata_json = {
            **(metadata.metadata_json or {}),
            "monitoring_status": "heightened",
            "last_reviewed_by": super_admin.id,
        }

    if db.scalar(select(GeospatialAOIFavorite).where(GeospatialAOIFavorite.aoi_id == aoi.id, GeospatialAOIFavorite.user_id == super_admin.id)) is None:
        db.add(
            GeospatialAOIFavorite(
                aoi_id=aoi.id,
                user_id=super_admin.id,
                is_pinned=True,
                pinned_at=datetime.utcnow() - timedelta(days=2),
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialAOINote).where(GeospatialAOINote.aoi_id == aoi.id).limit(1)) is None:
        parent = GeospatialAOINote(
            aoi_id=aoi.id,
            note_type="note",
            body="AOI under heightened monitoring due to volatile cloud coverage and price pressure alerts.",
            mentions_json=["@market_analyst", "@policy_reviewer"],
            assigned_user_id=super_admin.id,
            is_resolved=False,
            metadata_json={"category": "risk", "priority": "high"},
            created_by=super_admin.id,
            updated_by=super_admin.id,
        )
        db.add(parent)
        db.flush()
        db.add(
            GeospatialAOINote(
                aoi_id=aoi.id,
                parent_note_id=parent.id,
                note_type="comment",
                body="Confirmed with municipal encoder that next field submission includes updated parcel notes.",
                mentions_json=["@municipal_encoder"],
                assigned_user_id=None,
                is_resolved=False,
                metadata_json={"category": "follow-up"},
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialAOIAttachment).where(GeospatialAOIAttachment.aoi_id == aoi.id).limit(1)) is None:
        db.add(
            GeospatialAOIAttachment(
                aoi_id=aoi.id,
                asset_type="photo",
                title="Seeded AOI Observation Photo",
                url="https://example.gov.ph/seed/geospatial/om-sj-photo-01.jpg",
                notes="Representative field image for seeded AOI timeline.",
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialAOIDocumentLink).where(GeospatialAOIDocumentLink.aoi_id == aoi.id).limit(1)) is None:
        doc = db.scalar(select(Document).order_by(Document.id).limit(1))
        db.add(
            GeospatialAOIDocumentLink(
                aoi_id=aoi.id,
                document_id=doc.id if doc else None,
                title="Seeded policy linkage",
                url=doc.file_path if doc else "https://example.gov.ph/seed/policy-link",
                notes="Reference for AOI monitoring policy and intervention context.",
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    runs = db.scalars(select(SatellitePipelineRun).order_by(SatellitePipelineRun.id)).all()
    for run in runs:
        if db.scalar(select(GeospatialRunEvent).where(GeospatialRunEvent.run_id == run.id).limit(1)) is not None:
            continue
        db.add(
            GeospatialRunEvent(
                run_id=run.id,
                phase="queue",
                status="queued",
                message="Seeded queue event",
                details_json={"seeded": True, "queue_priority": run.queue_priority},
                logged_at=(run.started_at or datetime.utcnow()) - timedelta(minutes=2),
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )
        db.add(
            GeospatialRunEvent(
                run_id=run.id,
                phase="execution",
                status=run.status,
                message="Seeded execution event",
                details_json={"seeded": True, "result_keys": list((run.results_json or {}).keys())},
                logged_at=run.finished_at or run.started_at or datetime.utcnow(),
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialRunPreset).where(GeospatialRunPreset.name == "Default Ingest Window").limit(1)) is None:
        db.add(
            GeospatialRunPreset(
                name="Default Ingest Window",
                run_type="ingest",
                description="Monthly ingest preset for Sentinel 1/2 sources.",
                sources_json={"sources": ["sentinel-2", "sentinel-1"]},
                parameters_json={"limit_per_source": 200},
                retry_strategy="exponential",
                queue_priority=80,
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )
    if db.scalar(select(GeospatialRunPreset).where(GeospatialRunPreset.name == "Feature Refresh Fast").limit(1)) is None:
        db.add(
            GeospatialRunPreset(
                name="Feature Refresh Fast",
                run_type="feature_refresh",
                description="Fast refresh preset for focused AOI updates.",
                sources_json={"sources": ["sentinel-2", "sentinel-1"]},
                parameters_json={"lookback_days": 14},
                retry_strategy="standard",
                queue_priority=60,
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialRunSchedule).where(GeospatialRunSchedule.name == "Monthly Provincial Geospatial Pipeline").limit(1)) is None:
        db.add(
            GeospatialRunSchedule(
                name="Monthly Provincial Geospatial Pipeline",
                run_type="ingest",
                aoi_id=None,
                cron_expression="0 2 1 * *",
                timezone="Asia/Manila",
                recurrence_template="monthly_start",
                retry_strategy="exponential",
                queue_priority=90,
                is_active=True,
                next_run_at=datetime.utcnow() + timedelta(days=7),
                last_run_at=datetime.utcnow() - timedelta(days=22),
                last_run_status="completed",
                sources_json={"sources": ["sentinel-2", "sentinel-1"]},
                parameters_json={"limit_per_source": 200},
                notify_channels_json={"channels": ["email:ops@onionwatch.ph"]},
                notes="Seeded monthly geospatial ingest schedule.",
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialFilterPreset).where(GeospatialFilterPreset.user_id == super_admin.id, GeospatialFilterPreset.name == "Cloudy Sentinel Scenes").limit(1)) is None:
        db.add(
            GeospatialFilterPreset(
                user_id=super_admin.id,
                preset_type="scene",
                name="Cloudy Sentinel Scenes",
                filters_json={"scene_source": "sentinel-2", "scene_search": "S2", "scene_sort_by": "cloud_score", "scene_sort_dir": "desc"},
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    if db.scalar(select(GeospatialFilterPreset).where(GeospatialFilterPreset.user_id == super_admin.id, GeospatialFilterPreset.name == "Low Confidence Features").limit(1)) is None:
        db.add(
            GeospatialFilterPreset(
                user_id=super_admin.id,
                preset_type="feature",
                name="Low Confidence Features",
                filters_json={"feature_sort_by": "observation_confidence_score", "feature_sort_dir": "asc", "feature_search": "sentinel"},
                created_by=super_admin.id,
                updated_by=super_admin.id,
            )
        )

    db.flush()

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


def _ensure_user(
    db: Session,
    email: str,
    full_name: str,
    municipality_id: int | None,
    role: Role,
    organization_id: int | None = None,
) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        if organization_id is not None and user.organization_id != organization_id:
            user.organization_id = organization_id
        if not db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)):
            db.add(UserRole(user_id=user.id, role_id=role.id))
            db.flush()
        return user

    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(DEMO_PASSWORD),
        municipality_id=municipality_id,
        organization_id=organization_id,
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

    provincial_org = db.scalar(select(StakeholderOrganization).where(StakeholderOrganization.name == "Occidental Mindoro Provincial Agriculture Office"))
    if not provincial_org:
        provincial_org = StakeholderOrganization(name="Occidental Mindoro Provincial Agriculture Office", organization_type="government")
        db.add(provincial_org)
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

    municipal_org_map: dict[str, StakeholderOrganization] = {}
    for code, name in MUNICIPALITIES:
        org_name = f"{name} Municipal Agriculture Office"
        municipality = municipality_map[code]
        municipal_org = db.scalar(select(StakeholderOrganization).where(StakeholderOrganization.name == org_name))
        if not municipal_org:
            municipal_org = StakeholderOrganization(
                name=org_name,
                organization_type="government",
                municipality_id=municipality.id,
            )
            db.add(municipal_org)
            db.flush()
        elif municipal_org.municipality_id != municipality.id:
            municipal_org.municipality_id = municipality.id
        municipal_org_map[code] = municipal_org

    # Demo users per role.
    _ensure_user(db, "super_admin@onionwatch.ph", "Super Admin", None, roles["super_admin"], organization_id=provincial_org.id)
    _ensure_user(db, "provincial_admin@onionwatch.ph", "Provincial Admin", None, roles["provincial_admin"], organization_id=provincial_org.id)
    _ensure_user(
        db,
        "municipal_encoder@onionwatch.ph",
        "Municipal Encoder",
        municipality_map["OM-SJ"].id,
        roles["municipal_encoder"],
        organization_id=municipal_org_map["OM-SJ"].id,
    )
    _ensure_user(
        db,
        "warehouse_operator@onionwatch.ph",
        "Warehouse Operator",
        municipality_map["OM-MB"].id,
        roles["warehouse_operator"],
        organization_id=municipal_org_map["OM-MB"].id,
    )
    _ensure_user(db, "market_analyst@onionwatch.ph", "Market Analyst", None, roles["market_analyst"], organization_id=provincial_org.id)
    _ensure_user(db, "policy_reviewer@onionwatch.ph", "Policy Reviewer", None, roles["policy_reviewer"], organization_id=provincial_org.id)
    _ensure_user(db, "executive_viewer@onionwatch.ph", "Executive Viewer", None, roles["executive_viewer"], organization_id=provincial_org.id)
    _ensure_user(db, "auditor@onionwatch.ph", "Auditor", None, roles["auditor"], organization_id=provincial_org.id)
    ensure_default_threshold_configs(db)
    ensure_default_report_recipient_groups(db, organization_id=provincial_org.id)

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

            if month == months[-1] and municipality == municipalities[0]:
                stock_value = round(stock_value * 2.8, 2)
                release_value = round(max(0.1, release_value * 0.03), 2)

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

            if month == months[-1] and municipality == municipalities[0]:
                farmgate = round(farmgate + 12.0, 2)
                wholesale = round(wholesale + 18.0, 2)
                retail = round(retail + 35.0, 2)

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
    _ensure_demo_geospatial_aoi(db)
    _ensure_demo_geospatial_features(db)
    _ensure_demo_geospatial_runs(db)
    _ensure_demo_geospatial_collaboration(db)
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
