# Geospatial Ops Records

Use this folder for execution artifacts referenced by rollout and incident runbooks.

## Required subfolders

- `geospatial-rollout/`
- `geospatial-kpi/`
- `geospatial-incidents/`
- `release/`

## Naming convention

- Use `YYYY-MM-DD` date prefixes.
- Include wave or incident identifiers in folder names.
- Keep machine-readable exports (`.csv`, `.json`) with matching summary notes (`.md`).

## Minimum artifacts

Rollout wave:

- readiness checklist
- go/no-go memo
- KPI baseline snapshot
- wave retrospective

KPI publication:

- scorecard CSV
- variance notes
- corrective action log

Incident:

- timeline
- evidence snapshot bundle
- communication log
- corrective actions

Release:

- validation bundle (typecheck/build/tests/e2e/lint)
- deployment render/apply evidence
- rollout and rollback command log
