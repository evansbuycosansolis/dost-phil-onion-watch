# Local Development

## Prerequisites

- Node.js 22+
- pnpm 9+
- Python 3.11+
- Docker Desktop (recommended)

## Option A: Docker-first

1. Copy env templates:
   - `apps/api/.env.example` -> `apps/api/.env`
   - `apps/web/.env.example` -> `apps/web/.env.local`
2. Build and start services:
   - `docker compose up --build`
3. Access:
   - Web: `http://localhost:3000`
   - API docs: `http://localhost:8000/docs`

## Option B: Local process mode

### API

1. `cd apps/api`
2. `python -m venv .venv`
3. Activate venv
4. `pip install -r requirements.txt`
5. `alembic upgrade head`
6. `python ../../scripts/seed_api.py`
7. `uvicorn app.main:app --reload --port 8000`

### Web

1. From repo root: `pnpm install`
2. `pnpm --filter @phil-onion-watch/web dev`

## Demo credentials

Default password for seeded accounts: `ChangeMe123!`

- `super_admin@onionwatch.ph`
- `provincial_admin@onionwatch.ph`
- `municipal_encoder@onionwatch.ph`
- `warehouse_operator@onionwatch.ph`
- `market_analyst@onionwatch.ph`
- `policy_reviewer@onionwatch.ph`
- `executive_viewer@onionwatch.ph`
- `auditor@onionwatch.ph`

## Useful local commands

- Seed + bootstrap API: `python scripts/seed_api.py`
- Trigger monthly pipeline: `python scripts/run_monthly_pipeline.py`
- Start background scheduler worker: `python -m app.jobs.worker` (from `apps/api`)
- Run API tests: `pytest apps/api/app/tests -q`
- Build workspace: `pnpm build`
