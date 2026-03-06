# System Overview

## Monorepo boundaries

`phil-onion-watch` is organized as a production-shaped monorepo with explicit separation between UI, API, shared contracts, and infrastructure:

- `apps/web`: Next.js App Router frontend for public login and protected dashboards.
- `apps/api`: FastAPI backend implementing operational CRUD, intelligence services, RBAC, and audit.
- `packages/*`: shared TypeScript contracts, UI primitives, domain constants, config, API client, and prompt templates.
- `data/*`: seed sources, fixtures, and reference documents.
- `infra/*`: Dockerfiles, nginx config, and deployment placeholders.

## Service roles

### Frontend (`apps/web`)

- Uses React Query + typed hooks from `@phil-onion-watch/api-client`.
- Routes grouped into public and dashboard segments.
- Dashboard shell enforces token presence and role-aware navigation.

### Backend (`apps/api`)

- Postgres (or sqlite for tests) is operational truth.
- FastAPI routers expose `api/v1/*` families for domain operations and read-only dashboard aggregators.
- Services encapsulate forecasting, anomaly detection, alert generation, report generation, and document indexing.
- RBAC is fail-closed via reusable `require_role` dependency.
- Audit events are emitted for critical mutations.

### Document intelligence

- Postgres stores document metadata and chunks.
- FAISS (or numpy fallback) stores/retrieves vector representations.
- Search results return citation-backed snippets for the Knowledge Center.

## Extensibility

The baseline is structured for:

- additional crops and commodity-specific models,
- expanded geography beyond Occidental Mindoro,
- mobile and partner integrations,
- external data feeds and intervention pipelines.
