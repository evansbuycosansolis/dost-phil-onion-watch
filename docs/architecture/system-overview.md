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
- Connector services encapsulate agency feed adapters, validation/normalization stages, and approval-gated application into operational truth tables.
- RBAC is fail-closed via reusable `require_role` dependency.
- Authentication supports local JWT login and optional OIDC IdP integration with role mapping and MFA checks for privileged roles.
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

### Geospatial surveillance

Phil Onion Watch includes an AOI-first geospatial surveillance design that ingests multi-source remote sensing observations (Sentinel-2, Sentinel-1, HLS, Landsat, MODIS) and converts them into auditable AOI-level features for dashboards and intelligence services.

See [docs/architecture/geospatial-surveillance.md](geospatial-surveillance.md).
