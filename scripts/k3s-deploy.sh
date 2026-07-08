#!/usr/bin/env bash
# k3s deployment script
# Usage: ./k3s-deploy.sh [dev|prod]
# in real prod, use Argo CD

set -e

# Deployment environment: dev (local registry) or prod (remote registry)
DEPLOY_ENV=${1:-prod}

# Load environment variables from .env file
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    set -a # auto-export all sourced variables
    source .env
    set +a
else
    echo "Warning: .env file not found. Variables might not be substituted correctly."
fi

# Configure registry and image pull policy per environment
if [ "$DEPLOY_ENV" = "dev" ]; then
    echo "Setting up development environment configuration..."
    export REGISTRY_DOMAIN=localhost
    export IMAGE_PULL_POLICY=Never
else
    echo "Setting up production environment configuration..."
    # REGISTRY_DOMAIN already exported via set -a from .env
    export IMAGE_PULL_POLICY=Always
fi

echo "Image registry: $REGISTRY_DOMAIN"
echo "Image pull policy: $IMAGE_PULL_POLICY"

echo ""
# Deploy to k3s cluster using Kustomize
echo "Deploying to k3s cluster using Kustomize ($DEPLOY_ENV)..."
echo ""

# Ensure the overlay directory exists
OVERLAY_DIR=".config/k8s/overlays/$DEPLOY_ENV"
if [ ! -d "$OVERLAY_DIR" ]; then
    echo "Error: Overlay directory $OVERLAY_DIR not found."
    exit 1
fi

# Check that the overlay .env file exists for secret generation
if [ ! -f "$OVERLAY_DIR/.env.$DEPLOY_ENV" ]; then
    echo "Error: Secret file $OVERLAY_DIR/.env.$DEPLOY_ENV not found."
    echo "Please create it before deploying (do not commit secrets to git)."
    exit 1
fi

echo "Creating/updating secret 'blog-secrets' from $OVERLAY_DIR/.env.$DEPLOY_ENV..."
kubectl create secret generic blog-secrets \
    --from-env-file="$OVERLAY_DIR/.env.$DEPLOY_ENV" \
    -n blog \
    --dry-run=client -o yaml | kubectl apply -f -

# Jobs are immutable; delete existing before applying new
echo "Preparing migration job..."
kubectl delete job blog-django-migrate -n blog --ignore-not-found

echo "Applying K8s manifests using Kustomize and envsubst..."
# Images and pull policy are fully controlled by the overlay kustomization.yaml.
# envsubst handles runtime variables like $BACKEND_DOMAIN and $ADMIN_EMAIL.
pushd "$OVERLAY_DIR" > /dev/null
kubectl kustomize . | envsubst | kubectl apply -f -
popd > /dev/null

echo ""
echo "Deployment completed!"
echo ""
echo "Check deployment status:"
echo "  kubectl get -n blog pods"
echo "  kubectl get -n blog svc"
echo "  kubectl get -n blog ingress"
echo "  kubectl get -n blog cronjob"
echo ""
echo "View logs:"
echo "  kubectl logs -f -n blog deployment/blog-django"
echo "  kubectl logs -f -n blog deployment/blog-celery-worker"
echo "  kubectl logs -f -n blog deployment/blog-celery-beat"
