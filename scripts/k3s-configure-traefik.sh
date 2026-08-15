#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

kubectl apply -k .config/k8s/traefik
kubectl wait \
    --for=jsonpath='{.spec.externalTrafficPolicy}'=Local \
    service/traefik \
    --namespace=kube-system \
    --timeout=180s

expected_argument="--entryPoints.websecure.http.middlewares=kube-system-cloudflare-and-cluster@kubernetescrd"
for _ in {1..90}; do
    if kubectl get deployment/traefik \
        --namespace=kube-system \
        --output=jsonpath='{.spec.template.spec.containers[0].args}' \
        | grep --fixed-strings --quiet -- "$expected_argument"; then
        kubectl rollout status deployment/traefik \
            --namespace=kube-system \
            --timeout=300s
        exit 0
    fi
    sleep 2
done

echo "Timed out waiting for the Traefik source allowlist middleware" >&2
exit 1
