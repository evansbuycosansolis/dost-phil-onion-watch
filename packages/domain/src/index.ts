export const ROLE_NAMES = [
  "super_admin",
  "provincial_admin",
  "municipal_encoder",
  "warehouse_operator",
  "market_analyst",
  "policy_reviewer",
  "executive_viewer",
  "auditor",
] as const;

export const ALERT_TYPES = [
  "shortage_risk",
  "oversupply_risk",
  "stock_retention_anomaly_risk",
  "price_pressure_risk",
  "import_timing_risk",
  "reporting_compliance_risk",
] as const;

export const ALERT_SEVERITY = ["low", "medium", "high", "critical"] as const;

export const ANOMALY_CATEGORIES = [
  "stock_release_mismatch",
  "price_stock_conflict",
  "import_harvest_collision",
  "price_spread_outlier",
  "stock_movement_discrepancy",
] as const;

export const REPORT_CATEGORIES = [
  "provincial_exec_summary",
  "municipality_summary",
  "warehouse_utilization",
  "price_trend",
  "alert_digest",
] as const;

export const INTERVENTION_ACTIONS = [
  "price_monitoring",
  "supply_release_directive",
  "import_review",
  "market_inspection",
  "storage_audit",
] as const;
