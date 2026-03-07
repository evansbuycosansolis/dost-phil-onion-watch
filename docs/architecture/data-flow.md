# Data Flow

## End-to-end monthly intelligence loop

1. **Ingestion and submissions**
   - Municipal and warehouse users submit production, stock, release, pricing, and import updates.
   - Mobile clients submit batched payloads through `POST /api/v1/production/mobile-sync` using per-item idempotency keys and conflict checks (`observed_server_updated_at`).
   - Agency connectors ingest source-specific feed payloads (`da_price_feed`, `boc_import_feed`, `nfa_warehouse_stock_feed`) through validation and normalization stages before entering governance workflows.
   - Submission provenance (`client_id`, `device_id`, `app_version`, `sync_batch_id`, request correlation id) is persisted in `source_submissions`.
   - Mutations are RBAC-guarded and audit-logged.

2. **Operational persistence**
   - Structured records are written to Postgres domain tables (`harvest_reports`, `warehouse_stock_reports`, `price_reports`, `import_records`, etc.).
   - Connector submissions are first staged in `source_submissions` and linked to `approval_workflows`; approved records are then applied to operational tables.

3. **Geospatial surveillance (AOI-level feature fusion)**
   - Multi-source satellite observations are normalized into scene metadata and extracted features per Area of Interest (AOI).
   - Optical and radar features are fused into auditable AOI-level signals (e.g., `crop_activity_score`, `vegetation_vigor_score`, `observation_confidence_score`).
   - These signals are exposed to dashboards and can be incorporated as supporting evidence in forecasting and anomaly detection.
   - See [docs/architecture/geospatial-surveillance.md](geospatial-surveillance.md).

4. **Aggregation layer**
   - Dashboard service computes read-only overviews for provincial, municipal, warehouse, prices, imports, alerts, reports, and admin views.

5. **Forecasting**
   - Forecast pipeline consumes historical production, stock, release, prices, imports, and demand signals.
   - Model ladder: seasonal-naive -> SARIMA (when available) -> ML regressor.
   - Outputs are persisted in `forecast_runs` and `forecast_outputs`.

6. **Anomaly detection**
   - Hybrid deterministic + statistical + optional Isolation Forest scoring runs on monthly data.
   - Events and scores are persisted in `anomaly_events` and `risk_scores`.

7. **Alert engine**
   - Business rules map forecast/anomaly/compliance/import signals into actionable alerts.
   - Alert lifecycle (`open`, `acknowledged`, `resolved`) is tracked with acknowledgements and audit trail.

8. **Knowledge retrieval**
   - Uploaded policy/report documents are first queued in `document_ingestion_jobs`.
   - Worker jobs process extraction/chunk embedding asynchronously with per-chunk retry safety.
   - Per-document progress and failure reasons are tracked on `documents`.
   - Successfully processed chunks are indexed into FAISS-backed retrieval.
   - Semantic search returns citation snippets with document references.

9. **Reports and artifacts**
   - Scheduled/manual generation persists report metadata and markdown artifacts.
   - Matching recipient groups (role and optional organization scope) are expanded into queued delivery logs.
   - Report exports are distributed via file-drop delivery (with optional webhook channel), with retries on transient failures.
   - Final delivery failures emit notifications and remain queryable as auditable logs.

10. **Pipeline orchestration**
   - `monthly_pipeline` job coordinates validation, recomputation, forecasting, anomalies, alerts, index refresh, and report generation.
   - `report_distribution` scheduled job queues undistributed reports and processes pending delivery logs.
   - Job status and run details are visible in Admin views.

11. **Observability and alerting**
   - Request middleware captures endpoint latency, status code, and correlation IDs.
   - Worker captures per-job success/failure counters and durations.
   - Correlation IDs connect API-triggered jobs for traceability.
   - Runtime monitor evaluates degraded endpoints / failing jobs and emits notifications.
