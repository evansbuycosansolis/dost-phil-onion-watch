#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
K8S_DIR="$ROOT_DIR/infra/deployment/k8s"

echo "[deploy] applying namespace/config/deployments via kustomize"
kubectl apply -k "$K8S_DIR"

echo "[deploy] done"
kubectl -n phil-onion-watch get pods
