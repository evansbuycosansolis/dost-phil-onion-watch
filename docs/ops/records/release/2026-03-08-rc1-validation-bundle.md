# Release Validation Bundle

- Date: 2026-03-08
- Release candidate: `v0.1.0-rc1`
- Scope: release hardening, no new feature-track scope

## Validation gates

| Gate | Command | Result |
| --- | --- | --- |
| Workspace typecheck | `pnpm typecheck` | PASS |
| Workspace production build | `pnpm build` | PASS |
| Backend tests | `pytest -q` (apps/api) | PASS (`50 passed`) |
| Web E2E | `pnpm --filter @phil-onion-watch/web test:e2e` | PASS (`6 passed`) |
| Markdown lint | `pnpm dlx markdownlint-cli2 ...` | PASS (`0 errors`) |
| `datetime.utcnow()` debt | `rg "datetime\\.utcnow\\(" apps/api/app -n` | PASS (`0 matches`) |

## Deployment artifact checks

| Check | Command | Result |
| --- | --- | --- |
| kubectl client | `kubectl version --client` | PASS (`v1.34.1`) |
| kustomize render | `kubectl kustomize infra/deployment/k8s` | PASS |
| active context | `kubectl config current-context` | BLOCKED (`current-context is not set`) |
| cluster apply dry-run | `kubectl apply --dry-run=client -k infra/deployment/k8s` | BLOCKED (no API server/context) |

## Functional smoke coverage evidence

- Login flow: covered by `apps/web/e2e/release-confidence.spec.ts` (`seeded roles can login...`) - PASS.
- Geospatial run drilldown: covered by `apps/web/e2e/geospatial-aois.spec.ts` (`Open drilldown`, run page, artifact center) - PASS.
- KPI automation flow: covered by `apps/web/e2e/release-confidence.spec.ts` (`geo ops monthly KPI automation...`) - PASS.
- Worker monthly/scheduled jobs: covered by backend tests including scheduler/job execution paths - PASS.
- `/health` and `/metrics`: validated through application startup and API smoke in test runs; direct local script path was partially blocked by local DB host config outside compose.

## Notes

- Remaining warning noise is from `statsmodels` seasonal start-parameter warnings under small seed data windows.
- Cluster-level rollout evidence requires a configured Kubernetes context in the target environment.
