# Geospatial Operator Guide

## Operations & Governance screens

- `Rollout Waves`: `/dashboard/ops/geospatial/rollout`
  - Create wave records from rollout template
  - Edit owner/reviewer scope and gate criteria
  - Run gate evaluation (`draft/ready/passed/failed`)
- `KPI Scorecards`: `/dashboard/ops/geospatial/kpi`
  - Create monthly scorecards from KPI template
  - Compute threshold traffic lights (`green/yellow/red`)
  - Trigger monthly KPI automation and review task generation
- `Incidents`: `/dashboard/ops/geospatial/incidents`
  - Open/mitigate/resolve/postmortem incident lifecycle
  - Maintain severity, SLO target, evidence pack, comms log
  - Run SLO checks to create breach tasks
- `Validation`: `/dashboard/ops/geospatial/validation`
  - Create validation runs with model and threshold versions
  - Execute VA-T01..VA-T10 with pass/fail/skip results
  - Attach evidence links and signoff validation runs
- `Risk Register`: `/dashboard/ops/geospatial/risks`
  - Create/update risks with likelihood*impact rating
  - Escalate risks with workflow tasks
  - Close risks with resolution notes

## Core API endpoints

- Rollout: `/api/v1/geospatial/waves*`
- KPI: `/api/v1/geospatial/kpi/scorecards*`
- Incidents: `/api/v1/geospatial/incidents*`
- Validation: `/api/v1/geospatial/validation/*`
- Risk: `/api/v1/geospatial/risks*`
- Ops tasks: `/api/v1/geospatial/ops/tasks`
- Automation: `/api/v1/geospatial/automation/*`

## Scheduled automation

- `geospatial_kpi_generation` (monthly)
- `geospatial_risk_review_reminder` (daily)
- `geospatial_incident_slo_check` (15-minute cadence)

All jobs use existing retry policy (`JOB_MAX_RETRIES`, `JOB_RETRY_BACKOFF_SECONDS`) and failure notification hooks.
