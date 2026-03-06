from enum import StrEnum


class RoleName(StrEnum):
    SUPER_ADMIN = "super_admin"
    PROVINCIAL_ADMIN = "provincial_admin"
    MUNICIPAL_ENCODER = "municipal_encoder"
    WAREHOUSE_OPERATOR = "warehouse_operator"
    MARKET_ANALYST = "market_analyst"
    POLICY_REVIEWER = "policy_reviewer"
    EXECUTIVE_VIEWER = "executive_viewer"
    AUDITOR = "auditor"


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertType(StrEnum):
    SHORTAGE_RISK = "shortage_risk"
    OVERSUPPLY_RISK = "oversupply_risk"
    STOCK_RETENTION = "stock_retention_anomaly_risk"
    PRICE_PRESSURE = "price_pressure_risk"
    IMPORT_TIMING = "import_timing_risk"
    REPORTING_COMPLIANCE = "reporting_compliance_risk"


class AnomalyCategory(StrEnum):
    STOCK_RELEASE_MISMATCH = "stock_release_mismatch"
    PRICE_STOCK_CONFLICT = "price_stock_conflict"
    IMPORT_HARVEST_COLLISION = "import_harvest_collision"
    PRICE_SPREAD_OUTLIER = "price_spread_outlier"
    STOCK_MOVEMENT_DISCREPANCY = "stock_movement_discrepancy"


class ReportCategory(StrEnum):
    PROVINCIAL_EXEC_SUMMARY = "provincial_exec_summary"
    MUNICIPAL_SUMMARY = "municipal_summary"
    WAREHOUSE_UTILIZATION = "warehouse_utilization"
    PRICE_TREND = "price_trend"
    ALERT_DIGEST = "alert_digest"


class InterventionActionType(StrEnum):
    PRICE_MONITORING = "price_monitoring"
    SUPPLY_RELEASE_DIRECTIVE = "supply_release_directive"
    IMPORT_REVIEW = "import_review"
    MARKET_INSPECTION = "market_inspection"
    STORAGE_AUDIT = "storage_audit"
