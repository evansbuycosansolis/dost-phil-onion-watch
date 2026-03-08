# RC1 Rollout and Rollback Evidence

- Date: 2026-03-08
- Candidate: `v0.1.0-rc1`
- Namespace: `phil-onion-watch`

## Release control hardening applied

1. Deployment images pinned (no `latest`):
   - `ghcr.io/evansbuycosansolis/dost-phil-onion-watch-api:v0.1.0-rc1`
   - `ghcr.io/evansbuycosansolis/dost-phil-onion-watch-web:v0.1.0-rc1`
2. Production secret scaffold created:
   - `infra/deployment/k8s/secret.production.yaml`
3. Deployment runbook updated:
   - `infra/deployment/README.md`
4. Deployment docs linked to validation evidence:
   - `docs/ops/deployment.md`

## Rollout command log

Executed in release hardening session:

```bash
kubectl version --client
kubectl config current-context
kubectl kustomize infra/deployment/k8s
kubectl apply --dry-run=client -k infra/deployment/k8s
```

Observed outcome:

- Client tooling available.
- No current Kubernetes context configured in this environment.
- Manifest rendering succeeded (`kustomize` output resolved).
- Apply/dry-run cannot complete without cluster API context.

## Pending cluster execution checklist

Execute in target cluster environment:

```bash
kubectl apply -f infra/deployment/k8s/secret.yaml
kubectl apply -k infra/deployment/k8s
kubectl -n phil-onion-watch rollout status deploy/api
kubectl -n phil-onion-watch rollout status deploy/web
kubectl -n phil-onion-watch rollout status deploy/worker
```

Then run smoke checks from `infra/deployment/README.md`:

- `/health`
- `/metrics`
- `/login`
- worker scheduler logs
- geospatial run drilldown
- KPI automation

## Rollback command set

```bash
kubectl -n phil-onion-watch rollout undo deploy/api
kubectl -n phil-onion-watch rollout undo deploy/web
kubectl -n phil-onion-watch rollout undo deploy/worker
kubectl -n phil-onion-watch rollout status deploy/api
kubectl -n phil-onion-watch rollout status deploy/web
kubectl -n phil-onion-watch rollout status deploy/worker
```
