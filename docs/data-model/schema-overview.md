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

- `forecast_runs`, `forecast_outputs`
- `anomaly_events`, `risk_scores`
- `alerts`, `alert_acknowledgements`

## Governance

- `audit_logs`, `data_corrections`, `source_submissions`, `approval_workflows`

## Document intelligence

- `documents`, `document_chunks`, `document_index_runs`

## Ops and reporting

- `job_runs`, `report_records`

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
- Future schema evolution should use additive migrations with backward-compatible API changes.
