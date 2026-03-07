# RBAC and Audit

## Role model

Implemented roles:

- `super_admin`
- `provincial_admin`
- `municipal_encoder`
- `warehouse_operator`
- `market_analyst`
- `policy_reviewer`
- `executive_viewer`
- `auditor`

## Authorization posture

- **Fail-closed** by default.
- Route handlers must explicitly call `require_role(...)`.
- Missing role intersection returns `403`.
- Dashboard responses apply role scope filtering for municipal and warehouse operators.
- Optional OIDC login path supports external role claims mapped to local roles at login.
- Privileged OIDC role assignments require MFA claims (`amr`/`acr`/boolean claim checks) before token issuance.

## High-level permissions

- `super_admin`, `provincial_admin`: broad system and operational control.
- `municipal_encoder`: scoped data submission only.
- `warehouse_operator`: warehouse and related stock/report operations.
- `market_analyst`, `policy_reviewer`: analytics and review functions.
- `executive_viewer`: read-only dashboards.
- `auditor`: read-only governance and audit visibility.

## Audit policy

Audit events are emitted for key mutations including:

- user creation,
- municipal and operational submissions,
- stock and price updates,
- import creation,
- alert acknowledge/resolve transitions,
- document upload queueing, queue processing, and reindex,
- report generation,
- report distribution group create/update,
- report delivery queueing, retry scheduling, success, and terminal failure,
- admin pipeline and settings actions.
- anomaly threshold tuning and version updates.
- mobile sync batch processing with per-submission status events (`accepted`, `updated`, `duplicate`, `conflict`, `rejected`) including provenance tags.
- agency connector ingestion and approval decisions (`connector.ingestion.*`, `connector.approval.*`) with source-provenance metadata.

Each event stores:

- actor user id,
- action type,
- entity type/id,
- timestamp,
- before/after payloads (when applicable),
- correlation id,
- optional metadata payload.

## Operational observability controls

- Request-level correlation IDs are propagated through API responses (`x-correlation-id`).
- API and background jobs publish runtime metrics for latency, error rates, and failure rates.
- Admin-only observability endpoints expose degraded endpoint and failing job indicators.
- Notification webhook integration emits alerts for job failures and degraded service conditions.

Access to `GET /api/v1/audit/events` is restricted to governance-capable roles (`super_admin`, `provincial_admin`, `auditor`).
