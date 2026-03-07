# Schema Overview

## Core references

- `users`, `roles`, `user_roles`
- `stakeholder_organizations`
- `municipalities`, `barangays`, `markets`
- `warehouses`, `cold_storage_facilities`

## Farmer and production

- `farmer_profiles`, `farm_locations`, `planting_records`
- `harvest_reports`, `yield_estimates`

## Storage and movement

- `warehouse_stock_reports`, `cold_storage_stock_reports`
- `stock_release_logs`, `transport_logs`, `distribution_logs`

## Pricing and demand

- `farmgate_price_reports`, `wholesale_price_reports`, `retail_price_reports`
- `demand_estimates`

## Imports and interventions

- `import_records`, `shipment_arrivals`, `inspection_notes`
- `intervention_actions`

## Intelligence

- `forecast_runs`, `forecast_outputs`, `forecast_model_metrics`
- `anomaly_threshold_configs`, `anomaly_threshold_versions`
- `anomaly_events`, `risk_scores`
- `alerts`, `alert_acknowledgements`

## Governance

- `audit_logs`, `data_corrections`, `source_submissions`, `approval_workflows`
  - `source_submissions` stores staged mobile and agency-feed records with idempotency, provenance, and target-entity linkage.
  - `approval_workflows` governs pending connector submissions prior to operational table application.

## Document intelligence

- `documents`, `document_chunks`, `document_ingestion_jobs`, `document_index_runs`

## Geospatial surveillance (planned)

- AOI and boundary management
  - `geospatial_aois`, `geospatial_aoi_versions`
- Satellite provenance and feature fusion
  - `satellite_pipeline_runs`
  - `satellite_scenes`
  - `geospatial_features`

## Ops and reporting

- `job_runs`, `report_records`
- `report_recipient_groups`, `report_delivery_logs`

## Index strategy highlights

Indexes are explicitly created for:

- `reporting_month` fields across monthly datasets,
- municipality and warehouse scoped dimensions,
- alert `severity` and `status`,
- forecast period and run month,
- price `report_date`,
- import and shipment `arrival_date`.

## Change management

- Alembic migration `20260306_0001_initial` builds the full baseline schema.
- Alembic migration `20260306_0002_forecast_model_registry` adds model-performance registry and forecast-output model selection fields.
- Alembic migration `20260306_0003_anomaly_threshold_configs` adds threshold tuning configs with version history per anomaly class.
- Alembic migration `20260306_0004_document_ingestion_queue` adds queued ingestion jobs, progress tracking, and safe chunk retries.
- Alembic migration `20260306_0005_report_distribution` adds recipient grouping by role/organization and auditable report delivery logs with retry tracking.
- Alembic migration `20260306_0006_oidc_auth_controls` adds user OIDC subject/provider fields and last MFA verification timestamp.
- Alembic migration `20260306_0007_observability_job_correlation` adds correlation IDs to job runs for API-to-worker traceability.
- Alembic migration `20260306_0008_mobile_sync_provenance` adds idempotency/provenance fields to `source_submissions` (`sync_batch_id`, `idempotency_key`, `payload_hash`, client/device metadata, linked target entity ids, and conflict reason).
- Future schema evolution should use additive migrations with backward-compatible API changes.
