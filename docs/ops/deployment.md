# Deployment

## Container services

The baseline deployment includes:

- `web` (Next.js)
- `api` (FastAPI)
- `postgres`
- `redis`
- `worker` (APScheduler cron worker with retry/backoff and failure notifications)

## Docker build artifacts

- API image: `infra/docker/api.Dockerfile`
- Web image: `infra/docker/web.Dockerfile`
- Reverse-proxy template: `infra/nginx/default.conf`

## Production hardening checklist

1. Move secrets and credentials to managed secret store.
2. Use managed Postgres and Redis with backup policies.
3. Enforce TLS termination at load balancer / ingress.
4. Restrict CORS origins and remove wildcard policy.
5. Configure job scheduler (cron/k8s) for monthly pipeline.
5.1. If using this baseline worker, configure cron env vars:
   - `MONTHLY_PIPELINE_CRON`
   - `ALERT_REFRESH_CRON`
   - `REPORT_GENERATION_CRON`
   - `REINDEX_DOCUMENTS_CRON`
   - `JOB_MAX_RETRIES`, `JOB_RETRY_BACKOFF_SECONDS`
   - `NOTIFICATION_WEBHOOK_URL`
6. Enable centralized logging + audit retention policy.
7. Add object storage target for report/document artifacts.
8. Set up regular migration workflow (`alembic upgrade head`).

## CI/CD baseline

GitHub Actions workflow (`.github/workflows/ci.yml`) performs:

- pnpm workspace install,
- shared package build,
- web lint + typecheck,
- API dependency install + pytest.

## Environment variables

Use `.env.example` templates in `apps/api` and `apps/web` as the baseline contract for deployment configuration.
