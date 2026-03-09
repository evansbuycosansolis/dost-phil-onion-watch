# Deployment Baseline

This folder provides a production-shaped Kubernetes baseline for
Phil Onion Watch.

## Layout

- `k8s/namespace.yaml`: namespace and storage class defaults
- `k8s/configmap-api.yaml`: non-secret runtime configuration
- `k8s/secret-example.yaml`: example secret manifest (copy and edit)
- `k8s/secret.production.yaml`: production secret scaffold with explicit required keys
- `k8s/postgres-statefulset.yaml`: Postgres + PVC
- `k8s/redis-deployment.yaml`: Redis cache/broker
- `k8s/api-deployment.yaml`: FastAPI deployment
- `k8s/worker-deployment.yaml`: APScheduler worker deployment
- `k8s/web-deployment.yaml`: Next.js deployment
- `k8s/services.yaml`: internal/external services
- `k8s/ingress.yaml`: ingress routing
- `k8s/kustomization.yaml`: one-shot apply order
- `scripts/apply.sh` and `scripts/apply.ps1`: helper wrappers

## Prerequisites

- Kubernetes cluster with ingress controller
- Container registry with pushed images:
  - `ghcr.io/evansbuycosansolis/dost-phil-onion-watch-api:v0.1.0-rc1`
  - `ghcr.io/evansbuycosansolis/dost-phil-onion-watch-web:v0.1.0-rc1`
- `kubectl` access to the target cluster

## Configure secrets

1. Copy `k8s/secret.production.yaml` to `k8s/secret.yaml`.
2. Replace placeholders (`SECRET_KEY`, DB password, OIDC values, webhook URLs).
3. Apply secrets first:

```bash
kubectl apply -f infra/deployment/k8s/secret.yaml
```

## Deploy all resources

```bash
kubectl apply -k infra/deployment/k8s
```

Or with wrapper scripts:

```bash
./infra/deployment/scripts/apply.sh
```

```powershell
./infra/deployment/scripts/apply.ps1
```

## Post-deploy checks

```bash
kubectl -n phil-onion-watch get pods
kubectl -n phil-onion-watch get svc
kubectl -n phil-onion-watch get ingress
kubectl -n phil-onion-watch logs deploy/api --tail=100
kubectl -n phil-onion-watch logs deploy/worker --tail=100
```

## Release smoke checks

Run these after the rollout is healthy:

```bash
# API health + readiness + metrics
kubectl -n phil-onion-watch port-forward deploy/api 8000:8000
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
curl -fsS http://127.0.0.1:8000/metrics | head

# Web login
kubectl -n phil-onion-watch port-forward deploy/web 3000:3000
open http://127.0.0.1:3000/login

# Worker scheduler presence
kubectl -n phil-onion-watch logs deploy/worker --tail=200 | grep -E "Background worker scheduler started|geospatial_kpi_generation"
```

Then verify core product flows in the web UI:

- geospatial run drilldown (`/dashboard/geospatial/runs/{runId}`)
- geospatial KPI automation (`/dashboard/ops/geospatial/kpi`)
- report CSV/PDF export (`/dashboard/reports`)

## Rollout update flow

```bash
kubectl -n phil-onion-watch set image deploy/api api=ghcr.io/evansbuycosansolis/dost-phil-onion-watch-api:<tag>
kubectl -n phil-onion-watch set image deploy/web web=ghcr.io/evansbuycosansolis/dost-phil-onion-watch-web:<tag>
kubectl -n phil-onion-watch set image deploy/worker worker=ghcr.io/evansbuycosansolis/dost-phil-onion-watch-api:<tag>
kubectl -n phil-onion-watch rollout status deploy/api
kubectl -n phil-onion-watch rollout status deploy/web
kubectl -n phil-onion-watch rollout status deploy/worker
```
