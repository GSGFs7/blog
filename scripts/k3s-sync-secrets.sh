#!/usr/bin/env bash
# k3s secret synchronization script
# Usage:
#  1. create a .env.prod or .env.dev in your project home
#  2. run ./k3s-sync-secrets.sh [dev|prod]

set -e

# Deployment environment: dev or prod
DEPLOY_ENV=${1:-prod}
OVERLAY_ENV=".env.$DEPLOY_ENV"

# Ensure we are in the project root
cd "$(dirname "$0")/.."

if [ -f "$OVERLAY_ENV" ]; then
    echo "Loading environment variables from $OVERLAY_ENV..."
    set -a
    source "$OVERLAY_ENV"
    set +a
else
    echo "Error: $OVERLAY_ENV file not found."
    exit 1
fi

echo "Generating secret 'blog-secrets' for $DEPLOY_ENV environment..."
kubectl create secret generic blog-secrets \
    --namespace=blog \
    --from-literal=ADMIN_EMAIL="${ADMIN_EMAIL}" \
    --from-literal=API_KEY="${API_KEY}" \
    --from-literal=DATABASE_PASSWORD="${DATABASE_PASSWORD}" \
    --from-literal=DATABASE_USER="${DATABASE_USER}" \
    --from-literal=DEFAULT_FROM_EMAIL="${DEFAULT_FROM_EMAIL}" \
    --from-literal=DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS}" \
    --from-literal=DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS}" \
    --from-literal=DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY}" \
    --from-literal=FERNET_KEY="${FERNET_KEY}" \
    --from-literal=FERNET_OLD_KEYS="${FERNET_OLD_KEYS}" \
    --from-literal=FRONTEND_URL="${FRONTEND_URL}" \
    --from-literal=HUGGINGFACE_HUB_TOKEN="${HUGGINGFACE_HUB_TOKEN}" \
    --from-literal=LITELLM_API_KEY="${REMOTE_EMBEDDING_API_KEY}" \
    --from-literal=REMOTE_EMBEDDING_API_KEY="${REMOTE_EMBEDDING_API_KEY}" \
    --from-literal=RESEND_API_KEY="${RESEND_API_KEY}" \
    --from-literal=S3_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}" \
    --from-literal=S3_BUCKET_NAME="${S3_BUCKET_NAME}" \
    --from-literal=S3_ENDPOINT_URL="${S3_ENDPOINT_URL}" \
    --from-literal=S3_PUBLIC_DOMAIN="${S3_PUBLIC_DOMAIN}" \
    --from-literal=S3_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}" \
    --from-literal=SERVER_NAME="${SERVER_NAME}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "Secrets synchronized successfully for $DEPLOY_ENV environment!"
