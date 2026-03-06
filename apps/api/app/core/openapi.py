from __future__ import annotations

from typing import Any

from app.schemas.common import ErrorResponse


TAG_EXAMPLES: dict[str, dict[str, Any]] = {
    "auth": {"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in_minutes": 720},
    "users": {"id": 12, "email": "analyst@onionwatch.ph", "full_name": "Market Analyst", "roles": ["market_analyst"], "is_active": True},
    "municipalities": {"id": 1, "code": "OM-SJ", "name": "San Jose", "province": "Occidental Mindoro", "region": "MIMAROPA"},
    "farmers": {"id": 4, "farmer_code": "OM-SJ-F01", "full_name": "San Jose Farmer 1", "municipality_id": 1},
    "production": {"id": 42, "municipality_id": 1, "reporting_month": "2026-03-01", "volume_tons": 256.5},
    "warehouses": {"id": 2, "name": "Mamburao Onion Warehouse", "municipality_id": 2, "capacity_tons": 530.0},
    "cold-storage": {"id": 2, "name": "Mamburao Cold Storage", "capacity_tons": 240.0, "municipality_id": 2},
    "distribution": {"id": 22, "warehouse_id": 3, "reporting_month": "2026-03-01", "volume_tons": 91.2},
    "prices": {"id": 88, "municipality_id": 1, "report_date": "2026-03-01", "price_per_kg": 63.4},
    "imports": {"id": 9, "import_reference": "IMP-202603-OM", "origin_country": "India", "volume_tons": 355.0},
    "forecasting": {"run_id": 7, "status": "completed", "run_month": "2026-03-01"},
    "anomalies": {"id": 11, "anomaly_type": "stock_release_mismatch", "severity": "high", "scope_type": "warehouse"},
    "alerts": {"id": 14, "title": "Projected supply shortage risk", "severity": "high", "status": "open"},
    "dashboard": {"reporting_month": "2026-03-01", "total_harvest_volume_tons": 1293.7, "active_alerts": 6},
    "documents": {"id": 3, "title": "Warehouse Inspection Highlights", "status": "processed", "source_type": "seed_reference"},
    "reports": {"id": 13, "category": "provincial_exec_summary", "status": "generated", "file_path": "/workspace/data/fixtures/reports/provincial_exec_summary_2026-03-01.md"},
    "admin": {"users_count": 8, "pipeline_runs": [{"id": 4, "status": "completed"}]},
    "audit": {"id": 104, "action_type": "alert.resolve", "entity_type": "alert", "entity_id": "14"},
}


OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": "Authentication and session endpoints.\n\nExample response:\n```json\n{\"access_token\":\"eyJ...\",\"token_type\":\"bearer\"}\n```",
    },
    {
        "name": "users",
        "description": "User administration with role assignments.\n\nExample response:\n```json\n{\"id\":12,\"email\":\"analyst@onionwatch.ph\",\"roles\":[\"market_analyst\"]}\n```",
    },
    {
        "name": "municipalities",
        "description": "Municipality reference and governance scope data.\n\nExample response:\n```json\n{\"id\":1,\"code\":\"OM-SJ\",\"name\":\"San Jose\"}\n```",
    },
    {
        "name": "farmers",
        "description": "Farmer profile registration and listing.\n\nExample response:\n```json\n{\"id\":4,\"farmer_code\":\"OM-SJ-F01\"}\n```",
    },
    {
        "name": "production",
        "description": "Planting and harvest reporting endpoints.\n\nExample response:\n```json\n{\"id\":42,\"volume_tons\":256.5}\n```",
    },
    {
        "name": "warehouses",
        "description": "Warehouse metadata and stock report operations.\n\nExample response:\n```json\n{\"id\":2,\"name\":\"Mamburao Onion Warehouse\",\"capacity_tons\":530.0}\n```",
    },
    {
        "name": "cold-storage",
        "description": "Cold storage facilities and utilization reports.\n\nExample response:\n```json\n{\"id\":2,\"name\":\"Mamburao Cold Storage\",\"capacity_tons\":240.0}\n```",
    },
    {
        "name": "distribution",
        "description": "Stock release, transport, and distribution movement logs.\n\nExample response:\n```json\n{\"id\":22,\"volume_tons\":91.2}\n```",
    },
    {
        "name": "prices",
        "description": "Farmgate, wholesale, and retail price reports.\n\nExample response:\n```json\n{\"id\":88,\"price_per_kg\":63.4}\n```",
    },
    {
        "name": "imports",
        "description": "Import records and shipment visibility.\n\nExample response:\n```json\n{\"id\":9,\"import_reference\":\"IMP-202603-OM\",\"volume_tons\":355.0}\n```",
    },
    {
        "name": "forecasting",
        "description": "Forecast run orchestration and output retrieval.\n\nExample response:\n```json\n{\"run_id\":7,\"status\":\"completed\"}\n```",
    },
    {
        "name": "anomalies",
        "description": "Hybrid anomaly detection and scored events.\n\nExample response:\n```json\n{\"id\":11,\"anomaly_type\":\"stock_release_mismatch\",\"severity\":\"high\"}\n```",
    },
    {
        "name": "alerts",
        "description": "Risk alerts lifecycle with acknowledge/resolve operations.\n\nExample response:\n```json\n{\"id\":14,\"title\":\"Projected supply shortage risk\",\"status\":\"open\"}\n```",
    },
    {
        "name": "dashboard",
        "description": "Read-only dashboard aggregation endpoints.\n\nExample response:\n```json\n{\"reporting_month\":\"2026-03-01\",\"total_harvest_volume_tons\":1293.7}\n```",
    },
    {
        "name": "documents",
        "description": "Document ingestion, indexing, and semantic search.\n\nExample response:\n```json\n{\"id\":3,\"title\":\"Warehouse Inspection Highlights\",\"status\":\"processed\"}\n```",
    },
    {
        "name": "reports",
        "description": "Report generation, listing, and export services.\n\nExample response:\n```json\n{\"id\":13,\"category\":\"provincial_exec_summary\",\"status\":\"generated\"}\n```",
    },
    {
        "name": "admin",
        "description": "Administrative job and system-level operations.\n\nExample response:\n```json\n{\"users_count\":8,\"pipeline_runs\":[{\"id\":4,\"status\":\"completed\"}]}\n```",
    },
    {
        "name": "audit",
        "description": "Audit event stream for governance and compliance.\n\nExample response:\n```json\n{\"id\":104,\"action_type\":\"alert.resolve\",\"entity_type\":\"alert\"}\n```",
    },
]


def router_default_responses(tag: str) -> dict[int, dict[str, Any]]:
    success_example = TAG_EXAMPLES.get(tag, {"message": "ok"})
    return {
        200: {
            "description": f"{tag} successful response",
            "content": {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": success_example,
                }
            },
        },
        400: {"description": "Bad request", "model": ErrorResponse},
        401: {"description": "Unauthorized", "model": ErrorResponse},
        403: {"description": "Forbidden", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        422: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Internal server error", "model": ErrorResponse},
    }
