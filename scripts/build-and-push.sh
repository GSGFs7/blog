#!/usr/bin/env bash
# build and push images to registry
# used by Woodpecker CI

set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

COMMIT_HASH="${CI_COMMIT_SHA:-latest}"
REGISTRY_RETAIN_COMMITS="${REGISTRY_RETAIN_COMMITS:-20}"
REGISTRY_CLEANUP_ENABLED="${REGISTRY_CLEANUP_ENABLED:-true}"
REGISTRY_CLEANUP_REQUIRED="${REGISTRY_CLEANUP_REQUIRED:-false}"
REGISTRY_CERT_DIR=""
REGISTRY_CURL_CA_BUNDLE=""
MANIFEST_ACCEPT_HEADER="application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"

declare -a IMAGES=(
    ".config/k8s/containers/app.Dockerfile::app"
    ".config/k8s/containers/backup.Dockerfile::backup"
    ".config/k8s/containers/model-downloader.Dockerfile::model-downloader"
)

function write_secret_file() {
    local value=$1
    local path=$2

    if [ -n "$value" ]; then
        printf '%s\n' "$value" > "$path"
    else
        rm -f "$path"
    fi
}

# ca files in woodpecker is self signed only
function find_system_ca_bundle() {
    local bundle

    for bundle in \
        /etc/ssl/certs/ca-certificates.crt \
        /etc/pki/tls/certs/ca-bundle.crt \
        /etc/ssl/ca-bundle.pem \
        /etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem; do
        if [ -s "$bundle" ]; then
            printf '%s\n' "$bundle"
            return 0
        fi
    done

    return 1
}

function setup_registry_curl_ca_bundle() {
    local system_bundle
    local custom_ca="$REGISTRY_CERT_DIR/ca.crt"

    if system_bundle=$(find_system_ca_bundle); then
        REGISTRY_CURL_CA_BUNDLE="$REGISTRY_CERT_DIR/curl-ca-bundle.crt"
        cp "$system_bundle" "$REGISTRY_CURL_CA_BUNDLE"
        if [ -s "$custom_ca" ]; then
            printf '\n' >> "$REGISTRY_CURL_CA_BUNDLE"
            cat "$custom_ca" >> "$REGISTRY_CURL_CA_BUNDLE"
        fi
    elif [ -s "$custom_ca" ]; then
        REGISTRY_CURL_CA_BUNDLE="$custom_ca"
    fi
}

function setup_podman_cert() {
    BASE_DIR="$HOME/.config/containers/certs.d/$REGISTRY_DOMAIN/"
    REGISTRY_CERT_DIR="$BASE_DIR"
    mkdir -p "$BASE_DIR"
    write_secret_file "${REGISTRY_CA_CERT:-}" "$BASE_DIR/ca.crt"
    write_secret_file "${REGISTRY_CLIENT_CERT:-}" "$BASE_DIR/client.cert"
    write_secret_file "${REGISTRY_CLIENT_KEY:-}" "$BASE_DIR/client.key"
    if [ -f "$BASE_DIR/client.key" ]; then
        chmod 600 "$BASE_DIR/client.key"
    fi
    setup_registry_curl_ca_bundle
}

function check_cdn_bypass() {
    if [ -z "${REGISTRY_IP:-}" ] || [ -z "${REGISTRY_DOMAIN:-}" ]; then
        echo "CDN bypass check failed: REGISTRY_IP or REGISTRY_DOMAIN is empty"
        exit 1
    fi

    # Verify DNS resolution (should match /etc/hosts entries)
    local resolved_ips
    resolved_ips=$(getent ahosts "$REGISTRY_DOMAIN" | awk '{print $1}' | sort -u)

    local found_expected_ipv4=false
    local found_blackhole_ipv6=false

    for ip in $resolved_ips; do
        if [ "$ip" == "$REGISTRY_IP" ]; then
            found_expected_ipv4=true
        elif [[ "$ip" == "::1" || "$ip" == "127.0.0.1" ]]; then
            if [[ "$ip" == "::1" ]]; then found_blackhole_ipv6=true; fi
            echo "Verified local/loopback resolution: $ip"
        else
            echo "CDN bypass check failed: Unexpected IP found (LEAK DETECTED): $ip"
            exit 1
        fi
    done

    if [ "$found_expected_ipv4" != "true" ]; then
        echo "CDN bypass check failed: Expected IPv4 $REGISTRY_IP not found in resolution."
        exit 1
    fi

    if [ "$found_blackhole_ipv6" != "true" ]; then
        echo "CDN bypass check warning: IPv6 blackhole (::1) not found. IPv6 might leak if enabled!"
    fi

    echo "DNS resolution verified: $REGISTRY_DOMAIN is locked to $REGISTRY_IP (IPv4) and ::1 (IPv6)"

    local probe_image="$REGISTRY_DOMAIN/blog-app:latest"
    local output
    local status

    echo "Checking CDN bypass with podman: $probe_image"

    set +e
    output="$(skopeo inspect "docker://$probe_image" 2>&1)"
    status=$?
    set -e

    if [ "$status" -eq 0 ]; then
        echo "CDN bypass check passed: podman can inspect $probe_image"
        return
    fi

    if printf '%s\n' "$output" | grep -Eiq "manifest unknown|name unknown"; then
        echo "CDN bypass check passed: podman reached $REGISTRY_DOMAIN, but $probe_image does not exist"
        return
    fi

    echo "CDN bypass check failed: podman could not reach $REGISTRY_DOMAIN successfully"
    printf '%s\n' "$output"
    exit 1
}

function podman_login() {
    echo "Logging into $REGISTRY_DOMAIN..."
    podman login -u "$REGISTRY_USERNAME" -p "$REGISTRY_PASSWORD" "$REGISTRY_DOMAIN"
}

function _build_with_podman() {
    local name=$1
    local dockerfile=$2
    local target=$3

    # build image
    local build_args=(
        "build"
        "-f" "$dockerfile"
        "-t" "localhost/blog-$name:latest"
    )

    if [ -n "$target" ]; then
        build_args+=("--target" "$target")
    fi

    echo "Building $name using podman build..."
    podman "${build_args[@]}" .
}

function print_builder_info() {
    echo "Builder info:"
    podman info
}

function build_images() {
    echo "Building all images..."
    for image_info in "${IMAGES[@]}"; do
        IFS=':' read -r dockerfile target name <<< "$image_info"
        _build_with_podman "$name" "$dockerfile" "$target"
    done
    echo "All images built successfully!"
}

function push_images() {
    echo "Pushing images to registry..."
    for image_info in "${IMAGES[@]}"; do
        IFS=':' read -r dockerfile target name <<< "$image_info"
        local remote_tag_latest="$REGISTRY_DOMAIN/blog-$name:latest"
        local remote_tag_sha="$REGISTRY_DOMAIN/blog-$name:$COMMIT_HASH"

        podman tag "localhost/blog-$name:latest" "$remote_tag_latest"
        podman tag "localhost/blog-$name:latest" "$remote_tag_sha"

        # push
        echo "Pushing $name..."
        podman push "$remote_tag_latest"
        podman push "$remote_tag_sha"
    done
}

function registry_curl() {
    local args=(
        curl -fsS
        --retry 3
        --retry-delay 2
    )

    if [ -n "$REGISTRY_CURL_CA_BUNDLE" ]; then
        args+=(--cacert "$REGISTRY_CURL_CA_BUNDLE")
    fi

    if [ -s "$REGISTRY_CERT_DIR/client.cert" ] && [ -s "$REGISTRY_CERT_DIR/client.key" ]; then
        args+=(--cert "$REGISTRY_CERT_DIR/client.cert" --key "$REGISTRY_CERT_DIR/client.key")
    fi

    "${args[@]}" "$@"
}

# identification git's 40 hexadecimal characters
function is_commit_tag() {
    [[ "$1" =~ ^[0-9a-f]{40}$ ]]
}

# white list
function collect_registry_keep_tags() {
    local -n keep_tags_ref=$1

    # keep 'latest'
    keep_tags_ref["latest"]=1
    if [ "$COMMIT_HASH" != "latest" ]; then
        keep_tags_ref["$COMMIT_HASH"]=1
    fi

    # keep latest 20 git commit
    if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
        while IFS= read -r commit; do
            keep_tags_ref["$commit"]=1
        done < <(git rev-list --max-count="$REGISTRY_RETAIN_COMMITS" HEAD)
    fi

    # keep current running
    if [ -f ".config/k8s/overlays/prod/kustomization.yaml" ]; then
        while IFS= read -r deployed_tag; do
            if [ -n "$deployed_tag" ]; then
                keep_tags_ref["$deployed_tag"]=1
            fi
        done < <(awk '/newTag:/ {print $2}' .config/k8s/overlays/prod/kustomization.yaml)
    fi
}

# get registry image tags
function registry_tags_for_repo() {
    local repo=$1
    local tags_json

    if ! tags_json=$(registry_curl "https://$REGISTRY_DOMAIN/v2/$repo/tags/list"); then
        echo "Could not list tags for $repo" >&2
        return 1
    fi

    printf '%s' "$tags_json" | jq -r '.tags[]?'
}

function registry_digest_for_tag() {
    local repo=$1
    local tag=$2
    local headers
    local digest

    if ! headers=$(registry_curl \
        -I \
        -H "Accept: $MANIFEST_ACCEPT_HEADER" \
        "https://$REGISTRY_DOMAIN/v2/$repo/manifests/$tag"); then
        echo "Could not fetch manifest headers for $repo:$tag" >&2
        return 1
    fi

    digest=$(printf '%s\n' "$headers" | awk 'tolower($1) == "docker-content-digest:" {gsub("\r", "", $2); print $2; exit}')

    if [ -z "$digest" ]; then
        echo "Could not resolve digest for $repo:$tag" >&2
        return 1
    fi

    printf '%s\n' "$digest"
}

function delete_registry_digest() {
    local repo=$1
    local digest=$2

    registry_curl \
        -X DELETE \
        "https://$REGISTRY_DOMAIN/v2/$repo/manifests/$digest" > /dev/null
}

function cleanup_registry_repo() {
    local repo=$1
    # shellcheck disable=SC2178
    local -n keep_tags_ref=$2
    local tags_output
    local tag
    local digest
    local deleted_count=0
    declare -A digest_tags=()
    declare -A keep_digests=()

    echo "Checking registry retention for $repo..."
    if ! tags_output=$(registry_tags_for_repo "$repo"); then
        return 1
    fi

    while IFS= read -r tag; do
        [ -n "$tag" ] || continue

        if ! digest=$(registry_digest_for_tag "$repo" "$tag"); then
            return 1
        fi

        digest_tags["$digest"]+="${digest_tags[$digest]:+ }$tag"

        if [ -n "${keep_tags_ref[$tag]:-}" ] || ! is_commit_tag "$tag"; then
            keep_digests["$digest"]=1
        fi
    done <<< "$tags_output"

    for digest in "${!digest_tags[@]}"; do
        if [ -n "${keep_digests[$digest]:-}" ]; then
            echo "Keeping $repo digest $digest (tags: ${digest_tags[$digest]})"
            continue
        fi

        echo "Deleting stale $repo digest $digest (tags: ${digest_tags[$digest]})"
        if [ "${REGISTRY_CLEANUP_DRY_RUN:-false}" = "true" ]; then
            continue
        fi

        if ! delete_registry_digest "$repo" "$digest"; then
            return 1
        fi

        deleted_count=$((deleted_count + 1))
    done

    echo "Deleted $deleted_count stale manifest(s) for $repo"
}

function cleanup_registry_images() {
    if [ "$REGISTRY_CLEANUP_ENABLED" != "true" ]; then
        echo "Registry cleanup disabled."
        return
    fi

    if ! command -v curl > /dev/null 2>&1 || ! command -v jq > /dev/null 2>&1; then
        echo "Registry cleanup requires curl and jq." >&2
        return 1
    fi

    declare -A keep_tags=()
    collect_registry_keep_tags keep_tags

    echo "Keeping registry tags: ${!keep_tags[*]}"
    for image_info in "${IMAGES[@]}"; do
        IFS=':' read -r dockerfile target name <<< "$image_info"
        cleanup_registry_repo "blog-$name" keep_tags || return 1
    done
}

function cleanup_registry_images_best_effort() {
    if [ "$REGISTRY_CLEANUP_REQUIRED" = "true" ]; then
        cleanup_registry_images
        return
    fi

    set +e
    cleanup_registry_images
    local status=$?
    set -e

    if [ "$status" -ne 0 ]; then
        echo "Registry cleanup failed with status $status; image push already completed, continuing."
    fi
}

function main() {
    print_builder_info
    setup_podman_cert
    check_cdn_bypass
    #podman_login
    build_images
    push_images
    cleanup_registry_images_best_effort
}

main
