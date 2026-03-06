# Data Flow

## End-to-end monthly intelligence loop

1. **Ingestion and submissions**
   - Municipal and warehouse users submit production, stock, release, pricing, and import updates.
   - Mutations are RBAC-guarded and audit-logged.

2. **Operational persistence**
   - Structured records are written to Postgres domain tables (`harvest_reports`, `warehouse_stock_reports`, `price_reports`, `import_records`, etc.).

3. **Aggregation layer**
   - Dashboard service computes read-only overviews for provincial, municipal, warehouse, prices, imports, alerts, reports, and admin views.

4. **Forecasting**
   - Forecast pipeline consumes historical production, stock, release, prices, imports, and demand signals.
   - Model ladder: seasonal-naive -> SARIMA (when available) -> ML regressor.
   - Outputs are persisted in `forecast_runs` and `forecast_outputs`.

5. **Anomaly detection**
   - Hybrid deterministic + statistical + optional Isolation Forest scoring runs on monthly data.
   - Events and scores are persisted in `anomaly_events` and `risk_scores`.

6. **Alert engine**
   - Business rules map forecast/anomaly/compliance/import signals into actionable alerts.
   - Alert lifecycle (`open`, `acknowledged`, `resolved`) is tracked with acknowledgements and audit trail.

7. **Knowledge retrieval**
   - Uploaded policy/report documents are chunked, embedded, and indexed.
   - Semantic search returns citation snippets with document references.

8. **Reports and artifacts**
   - Scheduled/manual generation persists report metadata and markdown artifacts.
   - Reports Center consumes generated artifacts and history.

9. **Pipeline orchestration**
   - `monthly_pipeline` job coordinates validation, recomputation, forecasting, anomalies, alerts, index refresh, and report generation.
   - Job status and run details are visible in Admin views.
