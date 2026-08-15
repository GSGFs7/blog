#!/usr/bin/env bash
# k3s deployment script
# in real prod, use Argo CD

set -euo pipefail

DEPLOY_ENV=${1:-}
case "$DEPLOY_ENV" in
    dev | prod) ;;
    *)
        echo "Usage: $0 <dev|prod>" >&2
        exit 1
        ;;
esac

cd "$(dirname "$0")/.."

OVERLAY_DIR=".config/k8s/overlays/$DEPLOY_ENV"
OVERLAY_ENV="$OVERLAY_DIR/.env.$DEPLOY_ENV"
if [ ! -d "$OVERLAY_DIR" ]; then
    echo "Error: $OVERLAY_DIR does not exist." >&2
    exit 1
fi
if [ ! -f "$OVERLAY_ENV" ]; then
    echo "Error: $OVERLAY_ENV does not exist." >&2
    exit 1
fi

if [ "$DEPLOY_ENV" = "prod" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$OVERLAY_ENV"
    set +a

    missing_keys=()
    for key in BACKEND_DOMAIN ADMIN_EMAIL; do
        if [ ! -v "$key" ] || [ -z "${!key}" ]; then
            missing_keys+=("$key")
        fi
    done
    if [ "${#missing_keys[@]}" -gt 0 ]; then
        echo "Error: missing production template variables:" >&2
        printf '  %s\n' "${missing_keys[@]}" >&2
        exit 1
    fi
fi

echo "Deploying the $DEPLOY_ENV overlay..."

if [ "$DEPLOY_ENV" = "prod" ]; then
    ./scripts/k3s-configure-traefik.sh
fi

./scripts/k3s-sync-secrets.sh "$DEPLOY_ENV"
kubectl delete job blog-django-migrate --namespace=blog --ignore-not-found

if [ "$DEPLOY_ENV" = "dev" ]; then
    kubectl apply -k "$OVERLAY_DIR"
else
    # shellcheck disable=SC2016
    kubectl kustomize "$OVERLAY_DIR" \
        | envsubst '${BACKEND_DOMAIN} ${ADMIN_EMAIL}' \
        | kubectl apply -f -
fi

if ! kubectl wait \
    --for=condition=complete \
    job/blog-django-migrate \
    --namespace=blog \
    --timeout=300s; then
    kubectl logs job/blog-django-migrate --namespace=blog --tail=200
    exit 1
fi

if [ "$DEPLOY_ENV" = "dev" ]; then
    kubectl rollout restart \
        deployment/blog-pgbouncer \
        deployment/blog-django \
        deployment/blog-celery-worker \
        deployment/blog-celery-beat \
        deployment/blog-litellm \
        deployment/blog-llama-cpp \
        --namespace=blog
fi

kubectl rollout status deployment/blog-pgbouncer --namespace=blog --timeout=180s
kubectl rollout status deployment/blog-django --namespace=blog --timeout=300s

echo "Deployment completed."
kubectl get pods --namespace=blog
