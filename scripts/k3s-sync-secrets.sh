#!/usr/bin/env bash
# k3s secret synchronization script
# Usage:
#  1. create a .env.prod or .env.dev in your project home
#  2. run ./k3s-sync-secrets.sh [dev|prod]

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

OVERLAY_ENV=".config/k8s/overlays/$DEPLOY_ENV/.env.$DEPLOY_ENV"
if [ ! -f "$OVERLAY_ENV" ]; then
    echo "Error: $OVERLAY_ENV does not exist." >&2
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$OVERLAY_ENV"
set +a

if [ -z "${LITELLM_API_KEY:-}" ] && [ -n "${REMOTE_EMBEDDING_API_KEY:-}" ]; then
    LITELLM_API_KEY=$REMOTE_EMBEDDING_API_KEY
fi
if [ -z "${REMOTE_EMBEDDING_API_KEY:-}" ] && [ -n "${LITELLM_API_KEY:-}" ]; then
    REMOTE_EMBEDDING_API_KEY=$LITELLM_API_KEY
fi
if [ -z "${S3_PUBLIC_DOMAIN:-}" ] && [ -n "${S3_PUBLIC_URL:-}" ]; then
    S3_PUBLIC_DOMAIN=$S3_PUBLIC_URL
fi

required_keys=(
    DATABASE_PASSWORD
    DATABASE_USER
    DJANGO_SECRET_KEY
    FERNET_KEY
    LITELLM_API_KEY
    S3_ACCESS_KEY_ID
    S3_BUCKET_NAME
    S3_ENDPOINT_URL
    S3_SECRET_ACCESS_KEY
)
secret_keys=(
    ADMIN_EMAIL
    DATABASE_PASSWORD
    DATABASE_USER
    DEFAULT_FROM_EMAIL
    DJANGO_CSRF_TRUSTED_ORIGINS
    DJANGO_SECRET_KEY
    FERNET_KEY
    FERNET_OLD_KEYS
    HUGGINGFACE_HUB_TOKEN
    LITELLM_API_KEY
    REMOTE_EMBEDDING_API_KEY
    RESEND_API_KEY
    S3_ACCESS_KEY_ID
    S3_BUCKET_NAME
    S3_ENDPOINT_URL
    S3_PUBLIC_DOMAIN
    S3_SECRET_ACCESS_KEY
    SERVER_NAME
)

missing_keys=()
for key in "${required_keys[@]}"; do
    if [ ! -v "$key" ] || [ -z "${!key}" ]; then
        missing_keys+=("$key")
    fi
done
if [ "${#missing_keys[@]}" -gt 0 ]; then
    echo "Error: missing required variables in $OVERLAY_ENV:" >&2
    printf '  %s\n' "${missing_keys[@]}" >&2
    exit 1
fi

secret_env=$(mktemp)
trap 'rm -f "$secret_env"' EXIT
for key in "${secret_keys[@]}"; do
    if [ -v "$key" ]; then
        printf '%s=%s\n' "$key" "${!key}" >> "$secret_env"
    fi
done

kubectl apply -f .config/k8s/base/namespace.yaml
kubectl create secret generic blog-secrets \
    --namespace=blog \
    --from-env-file="$secret_env" \
    --dry-run=client \
    -o yaml \
    | kubectl apply -f -

echo "Secret blog/blog-secrets synchronized from $OVERLAY_ENV."
