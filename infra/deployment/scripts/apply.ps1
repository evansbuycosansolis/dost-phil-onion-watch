$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$K8sDir = Join-Path $RootDir "infra\deployment\k8s"

Write-Host "[deploy] applying namespace/config/deployments via kustomize"
kubectl apply -k $K8sDir

Write-Host "[deploy] done"
kubectl -n phil-onion-watch get pods
