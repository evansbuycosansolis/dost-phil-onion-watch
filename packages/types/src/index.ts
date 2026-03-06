export type RoleName =
  | "super_admin"
  | "provincial_admin"
  | "municipal_encoder"
  | "warehouse_operator"
  | "market_analyst"
  | "policy_reviewer"
  | "executive_viewer"
  | "auditor";

export type AlertSeverity = "low" | "medium" | "high" | "critical";
export type AlertStatus = "open" | "acknowledged" | "resolved";

export interface SessionUser {
  id: number;
  email: string;
  fullName: string;
  roles: RoleName[];
  municipalityId?: number;
}

export interface MunicipalCard {
  municipality_id: number;
  municipality_name: string;
  production_tons: number;
  stock_tons: number;
  avg_farmgate_price: number;
}

export interface ProvincialOverview {
  reporting_month: string;
  total_harvest_volume_tons: number;
  current_warehouse_stock_tons: number;
  cold_storage_utilization_pct: number;
  stock_release_volume_tons: number;
  forecast_next_month_supply_tons: number;
  active_alerts: number;
  anomaly_hotspots: string[];
  municipality_cards: MunicipalCard[];
}

export interface WarehouseOverviewRow {
  warehouse_id: number;
  warehouse_name: string;
  municipality_name: string;
  location: string;
  capacity_tons: number;
  current_stock_tons: number;
  utilization_pct: number;
  last_update?: string;
  release_trend_tons: number;
  anomaly_flag: boolean;
}

export interface ForecastOutput {
  id: number;
  municipality_id: number;
  period_start: string;
  period_end: string;
  next_month_supply_tons: number;
  next_quarter_trend: number;
  shortage_probability: number;
  oversupply_probability: number;
  confidence_score: number;
}

export interface AnomalyEvent {
  id: number;
  detected_at: string;
  reporting_month: string;
  anomaly_type: string;
  scope_type: string;
  severity: AlertSeverity;
  summary: string;
  municipality_id?: number;
  warehouse_id?: number;
  market_id?: number;
  metrics?: Record<string, unknown>;
}

export interface AlertItem {
  id: number;
  title: string;
  severity: AlertSeverity;
  alert_type: string;
  scope_type: string;
  status: AlertStatus;
  summary: string;
  recommended_action: string;
  municipality_id?: number;
  warehouse_id?: number;
  market_id?: number;
  opened_at: string;
}

export interface Municipality {
  id: number;
  code: string;
  name: string;
  province: string;
  region: string;
}

export interface Warehouse {
  id: number;
  name: string;
  municipality_id: number;
  location: string;
  capacity_tons: number;
  is_active: boolean;
}

export interface PricePoint {
  id?: number;
  municipality_id: number;
  report_date: string;
  reporting_month: string;
  price_per_kg: number;
}

export interface ImportRecord {
  id: number;
  import_reference: string;
  origin_country: string;
  arrival_date: string;
  reporting_month: string;
  volume_tons: number;
  status: string;
}

export interface DocumentSearchResult {
  document_id: number;
  document_title: string;
  chunk_id: number;
  chunk_index: number;
  score: number;
  snippet: string;
}

export interface ReportRecord {
  id: number;
  category: string;
  title: string;
  reporting_month: string;
  status: string;
  generated_at: string;
  file_path?: string;
}

export interface ReportExportMetadata {
  report_id: number;
  format: "csv" | "pdf";
  media_type: string;
  file_path: string;
  file_name: string;
}
