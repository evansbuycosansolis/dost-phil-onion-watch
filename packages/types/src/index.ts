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
  authSource?: string;
  mfaVerified?: boolean;
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
  selected_model?: string;
  selected_model_score?: number;
  fallback_order?: string[];
}

export interface ForecastModelCandidate {
  model_name: string;
  model_family: "baseline" | "statistical" | "ml" | string;
  is_available: boolean;
  prediction_next_month?: number;
  holdout_mae?: number;
  holdout_mape?: number;
  score?: number;
  rank?: number;
  selected: boolean;
}

export interface MunicipalityForecastDiagnostics {
  municipality_id: number;
  municipality_name: string;
  selected_model?: string;
  selected_score?: number;
  fallback_order: string[];
  candidates: ForecastModelCandidate[];
}

export interface ForecastDiagnostics {
  run_id?: number;
  selected_model_counts: Record<string, number>;
  model_avg_score: Record<string, number>;
  model_avg_holdout_mae: Record<string, number>;
  municipality_diagnostics: MunicipalityForecastDiagnostics[];
}

export interface ForecastRunSummary {
  id: number;
  run_at: string;
  run_month: string;
  model_used: string;
  status: string;
  metrics?: Record<string, unknown>;
}

export interface ForecastLatestResponse {
  run: ForecastRunSummary | null;
  outputs: ForecastOutput[];
  diagnostics?: ForecastDiagnostics | null;
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

export interface AnomalyThresholdConfig {
  id: number;
  anomaly_type: string;
  version: number;
  thresholds: Record<string, number | boolean>;
  is_active: boolean;
  change_reason?: string;
  last_changed_by?: number;
  updated_at: string;
}

export interface AnomalyThresholdVersion {
  id: number;
  anomaly_type: string;
  version: number;
  thresholds: Record<string, number | boolean>;
  changed_by?: number;
  change_reason?: string;
  changed_at: string;
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

export interface KnowledgeDocument {
  id: number;
  title: string;
  file_name: string;
  status: string;
  source_type: string;
  uploaded_at: string;
  summary?: string;
  progress_pct: number;
  total_chunks: number;
  processed_chunks: number;
  failed_chunks: number;
  failure_reason?: string;
  index_status: string;
}

export interface DocumentIngestionJob {
  id: number;
  document_id: number;
  status: string;
  queued_at: string;
  started_at?: string;
  finished_at?: string;
  attempt_count: number;
  max_attempts: number;
  total_chunks: number;
  processed_chunks: number;
  failed_chunks: number;
  last_error?: string;
  details?: Record<string, unknown>;
}

export type MobileSubmissionType =
  | "harvest_report"
  | "warehouse_stock_report"
  | "farmgate_price_report";

export type MobileSubmissionStatus =
  | "accepted"
  | "updated"
  | "duplicate"
  | "conflict"
  | "rejected";

export interface MobileSubmissionProvenance {
  source_channel: string;
  client_id: string;
  device_id: string;
  app_version?: string;
  submitted_at?: string;
}

export interface MobileSubmissionItem {
  idempotency_key: string;
  submission_type: MobileSubmissionType;
  observed_server_updated_at?: string;
  payload: Record<string, unknown>;
}

export interface MobileSyncRequest {
  contract_version?: string;
  sync_batch_id: string;
  provenance: MobileSubmissionProvenance;
  submissions: MobileSubmissionItem[];
}

export interface MobileSubmissionResult {
  idempotency_key: string;
  submission_type: MobileSubmissionType;
  status: MobileSubmissionStatus;
  source_submission_id?: number;
  entity_type?: string;
  entity_id?: string;
  server_updated_at?: string;
  conflict_reason?: string;
  message?: string;
}

export interface MobileSyncResponse {
  sync_batch_id: string;
  processed_at: string;
  summary: Record<string, number>;
  results: MobileSubmissionResult[];
}

export interface MobileSubmissionRecord {
  id: number;
  sync_batch_id?: string;
  submission_type: string;
  source_channel: string;
  source_name: string;
  client_id?: string;
  device_id?: string;
  app_version?: string;
  idempotency_key?: string;
  status: string;
  target_entity_type?: string;
  target_entity_id?: string;
  conflict_reason?: string;
  submitted_by?: number;
  submitted_at: string;
  created_at: string;
  updated_at: string;
  provenance?: Record<string, unknown>;
}

export interface ConnectorDefinition {
  key: string;
  source_name: string;
  display_name: string;
  description: string;
  submission_types: string[];
  adapter_version: string;
}

export interface ConnectorIngestionItemResult {
  external_id: string;
  status: string;
  submission_type?: string;
  source_submission_id?: number;
  approval_workflow_id?: number;
  reason?: string;
}

export interface ConnectorIngestionResponse {
  connector_key: string;
  sync_batch_id: string;
  dry_run: boolean;
  fetched_count: number;
  accepted_count: number;
  rejected_count: number;
  duplicate_count: number;
  conflict_count: number;
  pending_approval_count: number;
  workflow_created_count: number;
  results: ConnectorIngestionItemResult[];
}

export interface ConnectorSubmission {
  id: number;
  connector_key: string;
  source_name: string;
  submission_type: string;
  status: string;
  idempotency_key?: string;
  target_entity_type?: string;
  target_entity_id?: string;
  conflict_reason?: string;
  submitted_by?: number;
  submitted_at: string;
  approval_workflow_id?: number;
  approval_status?: string;
  provenance?: Record<string, unknown>;
}

export interface ConnectorApprovalWorkflow {
  workflow_id: number;
  status: string;
  requested_by?: number;
  reviewed_by?: number;
  requested_at: string;
  reviewed_at?: string;
  notes?: string;
  source_submission_id: number;
  connector_key: string;
  submission_type: string;
  source_submission_status: string;
  source_submission_conflict_reason?: string;
}

export interface ConnectorApprovalDecision {
  workflow_id: number;
  status: string;
  source_submission_id: number;
  source_submission_status: string;
  target_entity_type?: string;
  target_entity_id?: string;
  reviewed_at: string;
}

export interface ReportRecord {
  id: number;
  category: string;
  title: string;
  reporting_month: string;
  status: string;
  generated_at: string;
  file_path?: string;
  metadata?: Record<string, unknown>;
}

export interface ReportExportMetadata {
  report_id: number;
  format: "csv" | "pdf";
  media_type: string;
  file_path: string;
  file_name: string;
}

export interface ReportRecipientGroup {
  id: number;
  name: string;
  description?: string;
  report_category?: string;
  role_name?: string;
  organization_id?: number;
  delivery_channel: "file_drop" | "webhook" | string;
  export_format: "csv" | "pdf" | string;
  max_attempts: number;
  retry_backoff_seconds: number;
  notify_on_failure: boolean;
  is_active: boolean;
  last_used_at?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReportDeliveryLog {
  id: number;
  report_id: number;
  recipient_group_id: number;
  recipient_user_id: number;
  recipient_email: string;
  recipient_role?: string;
  recipient_organization_id?: number;
  delivery_channel: string;
  export_format: string;
  status: "queued" | "delivering" | "retrying" | "sent" | "failed" | string;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at?: string;
  dispatched_at: string;
  delivered_at?: string;
  last_error?: string;
  notification_sent_at?: string;
  payload?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReportDeliveryProcessResult {
  processed_count: number;
  sent_count: number;
  failed_count: number;
  retrying_count: number;
  deliveries: ReportDeliveryLog[];
}

export interface AuditEvent {
  id: number;
  actor_user_id?: number;
  action_type: string;
  entity_type: string;
  entity_id: string;
  timestamp: string;
  before_payload?: Record<string, unknown>;
  after_payload?: Record<string, unknown>;
  correlation_id?: string;
  metadata?: Record<string, unknown>;
}

export type AuditDiffChangeType = "added" | "removed" | "modified";

export interface AuditDiffEntry {
  path: string;
  change_type: AuditDiffChangeType;
  before_value?: unknown;
  after_value?: unknown;
}

export interface AuditDiffSummary {
  total_changes: number;
  added: number;
  removed: number;
  modified: number;
}

export interface AuditEventDiff {
  event: AuditEvent;
  summary: AuditDiffSummary;
  changes: AuditDiffEntry[];
}

export interface AdminForecastDiagnostics {
  run_id?: number;
  selected_model_counts: Record<string, number>;
  model_avg_score: Record<string, number>;
  model_avg_holdout_mae: Record<string, number>;
  municipalities_covered: number;
}

export interface AdminOverview {
  users_count: number;
  document_ingestion_status: {
    latest_run_id?: number;
    latest_status: string;
    num_chunks: number;
  };
  job_status: Array<{
    id: number;
    job_name: string;
    status: string;
    correlation_id?: string;
    started_at: string;
    finished_at?: string;
  }>;
  pipeline_runs: Array<{
    id: number;
    status: string;
    details?: Record<string, unknown>;
  }>;
  report_distribution_status: Record<string, number>;
  forecast_model_diagnostics: AdminForecastDiagnostics;
  system_settings: Record<string, unknown>;
}
