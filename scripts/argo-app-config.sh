#!/usr/bin/env bash
# apply Argo CD app

set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    set -a
    source .env
    set +a
else
    echo "Warning: .env file not found. Variables might not be substituted correctly."
fi

echo "apply to Argo CD..."
envsubst < scripts/argo-app-config.template.yaml | kubectl apply -f -
