#!/usr/bin/env bash
# k3s component build script
# Builds and imports all container images for k3s deployment
# in real prod, use Argo CD

set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

BUILD_ID="${CI_COMMIT_SHA:-$(git rev-parse HEAD)}"

# Image list: dockerfile_path:target:name
declare -a IMAGES=(
    ".config/k8s/containers/app.Dockerfile::app"
    ".config/k8s/containers/backup.Dockerfile::backup"
    ".config/k8s/containers/model-downloader.Dockerfile::model-downloader"
    ".config/k8s/containers/pgbouncer.Dockerfile::pgbouncer"
)

# Detect available container builder (podman preferred)
detect_container_builder() {
    if command -v podman &> /dev/null; then
        echo "podman"
    elif command -v docker &> /dev/null; then
        echo "docker"
    else
        echo "ERROR: Neither podman nor docker is installed" >&2
        exit 1
    fi
}

# Build image using podman
build_with_podman() {
    local name=$1
    local dockerfile=$2
    local target=$3
    local build_args=(
        "build"
        "-f" "$dockerfile"
        "-t" "localhost/blog-$name:latest"
    )
    if [ "$name" == "app" ]; then build_args+=("--build-arg" "BUILD_ID=$BUILD_ID"); fi
    if [ -n "$target" ]; then build_args+=("--target" "$target"); fi
    podman "${build_args[@]}" .
}

# Build image using docker
build_with_docker() {
    local name=$1
    local dockerfile=$2
    local target=$3
    local build_args=(
        "build"
        "-f" "$dockerfile"
        "-t" "localhost/blog-$name:latest"
    )
    if [ "$name" == "app" ]; then build_args+=("--build-arg" "BUILD_ID=$BUILD_ID"); fi
    if [ -n "$target" ]; then build_args+=("--target" "$target"); fi
    docker "${build_args[@]}" .
}

# Build all images in the list
build_images() {
    local builder=$1

    echo "Building images with $builder..."
    echo ""

    for image_info in "${IMAGES[@]}"; do
        IFS=':' read -r dockerfile target name <<< "$image_info"
        echo "Building $name image (target: ${target:-N/A})..."
        if [ "$builder" == "podman" ]; then
            build_with_podman "$name" "$dockerfile" "$target"
        elif [ "$builder" == "docker" ]; then
            build_with_docker "$name" "$dockerfile" "$target"
        fi
    done

    echo ""
    echo "All images built successfully!"
    echo ""
}

# Import images into k3s containerd
import_to_k3s() {
    local builder=$1

    for image_info in "${IMAGES[@]}"; do
        IFS=':' read -r dockerfile target name <<< "$image_info"
        echo "Importing localhost/blog-$name:latest to k3s..."
        $builder save "localhost/blog-$name:latest" | sudo k3s ctr images import -
    done
    echo ""
    echo "Images imported successfully!"
    echo ""
}

print_what_next() {
    echo "Deploy to k3s:"
    echo "  ./scripts/k3s-deploy.sh dev"
}

# Main execution
CONTAINER_BUILDER=$(detect_container_builder)
echo "Using $CONTAINER_BUILDER as container builder"

build_images "$CONTAINER_BUILDER"
import_to_k3s "$CONTAINER_BUILDER"
print_what_next
