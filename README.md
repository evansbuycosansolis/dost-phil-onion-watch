# DOST Phil Onion Watch

**Formal title:** DOST Phil Onion Watch: AI-Enabled Onion Supply Chain Monitoring, Forecasting, and Market Intelligence Platform for Occidental Mindoro

This monorepo is a production-shaped baseline for a government-grade onion supply transparency and market intelligence platform.

## Stack

- Frontend: Next.js (App Router), TypeScript, Tailwind, React Query
- Backend: FastAPI, SQLAlchemy, Alembic
- Data: PostgreSQL (operational truth), Redis (job/cache support), FAISS (document retrieval; numpy fallback)
- Monorepo: pnpm workspaces
- CI: GitHub Actions
- Containerization: Docker + docker-compose

## Repository layout

```text
phil-onion-watch/
├─ apps/
│  ├─ web/
│  └─ api/
├─ packages/
│  ├─ ui/
│  ├─ types/
│  ├─ config/
│  ├─ domain/
│  ├─ api-client/
│  └─ ai-prompts/
├─ docs/
├─ infra/
├─ scripts/
├─ data/
└─ .github/workflows/
```

## Quickstart (Docker)

1. Copy env templates:
   - `apps/api/.env.example` -> `apps/api/.env`
   - `apps/web/.env.example` -> `apps/web/.env.local`
2. Run:

```bash
docker compose up --build
```

3. Access:
- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## Quickstart (local process)

```bash
pnpm install
pnpm --filter @phil-onion-watch/web dev
```

In another terminal:

```bash
cd apps/api
python -m venv .venv
# activate .venv
pip install -r requirements.txt
alembic upgrade head
python ../../scripts/seed_api.py
uvicorn app.main:app --reload --port 8000
```

## Seeded login accounts

Default password: `ChangeMe123!`

- `super_admin@onionwatch.ph`
- `provincial_admin@onionwatch.ph`
- `municipal_encoder@onionwatch.ph`
- `warehouse_operator@onionwatch.ph`
- `market_analyst@onionwatch.ph`
- `policy_reviewer@onionwatch.ph`
- `executive_viewer@onionwatch.ph`
- `auditor@onionwatch.ph`

## OIDC (optional)

`/api/v1/auth/oidc/login` supports external identity-provider login with:

- OIDC discovery/JWKS token verification,
- external-to-local role mapping (`OIDC_ROLE_MAPPING`),
- MFA requirement checks for privileged roles (`OIDC_PRIVILEGED_ROLES`).

## Core API families

- `/api/v1/auth/*`
- `/api/v1/users/*`
- `/api/v1/municipalities/*`
- `/api/v1/farmers/*`
- `/api/v1/production/*`
- `/api/v1/warehouses/*`
- `/api/v1/cold-storage/*`
- `/api/v1/distribution/*`
- `/api/v1/prices/*`
- `/api/v1/imports/*`
- `/api/v1/forecasting/*`
- `/api/v1/anomalies/*`
- `/api/v1/alerts/*`
- `/api/v1/dashboard/*`
- `/api/v1/documents/*`
- `/api/v1/reports/*`
- `/api/v1/admin/*`
- `/api/v1/audit/*`

## Monthly pipeline

`app/jobs/monthly_pipeline.py` orchestrates:

1. submission validation marker
2. KPI refresh
3. forecasting
4. anomaly detection
5. alert generation
6. document index refresh
7. report generation
8. job run persistence

Run manually:

```bash
python scripts/run_monthly_pipeline.py
```

## Scheduled background worker

`app/jobs/worker.py` runs APScheduler cron jobs for:

- monthly pipeline execution,
- alert refresh,
- report generation,
- report distribution,
- document reindex,
- observability monitor and degraded-service alerting.

Retry and notification controls (via `apps/api/.env`):

- `JOB_MAX_RETRIES`
- `JOB_RETRY_BACKOFF_SECONDS`
- `NOTIFICATION_WEBHOOK_URL`

Run locally:

```bash
cd apps/api
python -m app.jobs.worker
```

## Report exports

Reports API now supports export metadata and downloadable artifacts:

- `GET /api/v1/reports/{report_id}/export/csv`
- `GET /api/v1/reports/{report_id}/export/pdf`
- `GET /api/v1/reports/{report_id}/download/csv`
- `GET /api/v1/reports/{report_id}/download/pdf`

## Mobile submission sync contract

Municipal/mobile clients can sync batched submissions through:

- `POST /api/v1/production/mobile-sync`
- `GET /api/v1/production/mobile-sync/submissions`

Contract behavior:

- per-item idempotency via `idempotency_key` and payload hash checks,
- optimistic conflict protection via `observed_server_updated_at`,
- provenance capture (`client_id`, `device_id`, `app_version`, `sync_batch_id`, correlation id),
- audit tagging per submission status and batch summary.

## Agency feed connector ingestion

Agency feed adapters support staged ingestion with validation, normalization, and approval:

- `GET /api/v1/admin/connectors`
- `POST /api/v1/admin/connectors/{connector_key}/ingest`
- `GET /api/v1/admin/connectors/submissions`
- `GET /api/v1/admin/connectors/approvals`
- `POST /api/v1/admin/connectors/approvals/{workflow_id}/approve`
- `POST /api/v1/admin/connectors/approvals/{workflow_id}/reject`

Supported connectors in this baseline:

- `da_price_feed`
- `boc_import_feed`
- `nfa_warehouse_stock_feed`

## Tests

API tests are under `apps/api/app/tests` and cover:

- auth success/failure
- role enforcement
- dashboard overviews
- forecasting run
- anomaly run
- alert acknowledge/resolve
- document upload/search
- audit log emission

```bash
pytest apps/api/app/tests -q
```

Web E2E release confidence tests (cross-role login, dashboard navigation, alerts lifecycle, report export):

```bash
pnpm --filter @phil-onion-watch/web exec playwright install --with-deps chromium
pnpm --filter @phil-onion-watch/web test:e2e
```

## Observability

- `GET /metrics` exports request, endpoint, and background job metrics (Prometheus text format).
- `GET /api/v1/admin/observability/overview` provides actionable error-rate/latency/job-failure summaries.
- `GET /api/v1/admin/observability/traces/{correlation_id}` links API requests and job runs through correlation IDs.

## Notes

- Operational truth remains in relational tables (Postgres).
- Vector index is limited to unstructured document retrieval.
- RBAC is fail-closed and mutations emit audit events.
