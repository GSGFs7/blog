#!/usr/bin/env python

import json
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypedDict
from urllib.parse import quote, urlsplit

import boto3
import httpx2
from blake3 import blake3
from botocore.config import Config
from botocore.exceptions import ClientError

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
RELEASE_CACHE_CONTROL = "no-store"
MAX_WORKERS = 16
S3_REGION = "auto"
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SERVER_ONLY_ASSETS = {
    "ssr/solid-islands.json",
    "ssr/ssr.mjs",
}

MIME_TYPES = {
    ".asc": "application/pgp-signature",
    ".css": "text/css",
    ".ico": "image/vnd.microsoft.icon",
    ".js": "text/javascript",
    ".json": "application/json",
    ".md": "text/markdown",
    ".mjs": "text/javascript",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".txt": "text/plain",
    ".wasm": "application/wasm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class AssetRecord(TypedDict):
    path: str
    blake3: str
    size: int


class ReleaseManifest(TypedDict):
    schema: int
    commit: str
    assets: list[AssetRecord]


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    record: AssetRecord
    uploaded: bool


def _content_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in MIME_TYPES:
        return MIME_TYPES[suffix]
    # fallback
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or not path.parts or path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"Invalid static asset path: {value}")
    return path.as_posix()


def _should_publish(path: str) -> bool:
    relative = PurePosixPath(path)
    name = relative.name
    return relative.suffix != ".map" and not (
        name == "manifest.json"
        or (name.startswith("manifest.") and name.endswith(".json"))
    )


def collect_asset_paths(root: Path) -> list[Path]:
    root = root.resolve()
    # manifest 0, django
    django_manifest = json.loads(
        (root / "staticfiles.json").read_text(encoding="utf-8")
    )
    relative_paths = {
        _relative_path(target)
        for source, target in django_manifest["paths"].items()
        if source not in SERVER_ONLY_ASSETS
    }

    # manifest 1, vite
    vite_manifest = json.loads(
        (root / "dist" / "manifest.json").read_text(encoding="utf-8")
    )
    for entry in vite_manifest.values():
        relative_paths.add(_relative_path(f"dist/{entry['file']}"))
        for field in ("css", "assets"):
            relative_paths.update(
                _relative_path(f"dist/{value}") for value in entry.get(field, ())
            )

    relative_paths = {path for path in relative_paths if _should_publish(path)}
    files: list[Path] = []
    missing: list[str] = []
    for relative in sorted(relative_paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(f"Static asset escapes root: {relative}") from exc
        # it should a file
        if not path.is_file():
            missing.append(relative)
        else:
            files.append(path)

    if missing:
        raise RuntimeError(f"Static assets are missing: {', '.join(missing)}")
    if not files:
        raise RuntimeError("No static assets were selected for publication")
    return files


def _file_digest(path: Path) -> str:
    digest = blake3()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def object_key(prefix: str, relative_path: str) -> str:
    relative = _relative_path(relative_path)
    normalized_prefix = prefix.strip("/")
    if normalized_prefix:
        normalized_prefix = _relative_path(normalized_prefix)
    return f"{normalized_prefix}/{relative}" if normalized_prefix else relative


def public_asset_url(base_url: str, relative_path: str) -> str:
    relative = _relative_path(relative_path)
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError(f"Invalid static asset public URL: {base_url}")
    return f"{base_url.rstrip('/')}/{quote(relative, safe='/')}"


def _is_precondition_failed(error: ClientError) -> bool:
    response = error.response
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    code = response.get("Error", {}).get("Code")
    return status == 412 or code == "PreconditionFailed"


def _raise_upload_error(error: ClientError) -> None:
    if error.response.get("Error", {}).get("Code") == "SignatureDoesNotMatch":
        raise RuntimeError(
            "R2 rejected the S3 signature. Verify the R2 S3 endpoint and the "
            "Access Key ID/Secret Access Key configured in CI."
        ) from error
    raise error


def _validate_stored_object(
    response,
    *,
    key: str,
    digest: str,
    size: int,
    content_type: str,
    cache_control: str,
) -> None:
    metadata = response.get("Metadata", {})
    if metadata.get("blake3") != digest:
        raise RuntimeError(f"Immutable asset collision: {key}")
    if response.get("ContentLength") != size:
        raise RuntimeError(f"Static asset size mismatch: {key}")
    if response.get("CacheControl") != cache_control:
        raise RuntimeError(f"Static asset cache policy mismatch: {key}")

    actual_content_type = response.get("ContentType", "").split(";", 1)[0].lower()
    expected_content_type = content_type.split(";", 1)[0].lower()
    if actual_content_type != expected_content_type:
        raise RuntimeError(f"Static asset content type mismatch: {key}")


def upload_asset(
    client,
    *,
    bucket: str,
    key: str,
    path: Path,
    relative_path: str,
) -> UploadOutcome:
    digest = _file_digest(path)
    size = path.stat().st_size
    content_type = _content_type(path)
    uploaded = True

    try:
        with path.open("rb") as body:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                IfNoneMatch="*",
                ContentType=content_type,
                CacheControl=IMMUTABLE_CACHE_CONTROL,
                Metadata={"blake3": digest},
            )
    except ClientError as error:
        if not _is_precondition_failed(error):
            _raise_upload_error(error)
        uploaded = False

    stored = client.head_object(Bucket=bucket, Key=key)
    _validate_stored_object(
        stored,
        key=key,
        digest=digest,
        size=size,
        content_type=content_type,
        cache_control=IMMUTABLE_CACHE_CONTROL,
    )
    return UploadOutcome(
        record={"path": relative_path, "blake3": digest, "size": size},
        uploaded=uploaded,
    )


def check_asset(
    client: httpx2.Client,
    *,
    url: str,
    allowed_origin: str,
    content_type: str,
) -> None:
    response = client.head(url, headers={"Origin": allowed_origin})
    response.raise_for_status()

    # checks

    cache_directives = {
        directive.strip().lower()
        for directive in response.headers.get("Cache-Control", "").split(",")
    }
    required_cache_directives = {"public", "max-age=31536000", "immutable"}
    if not required_cache_directives.issubset(cache_directives):
        raise RuntimeError(f"Static asset cache policy is invalid: {url}")

    actual_content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
    expected_content_type = content_type.split(";", 1)[0]
    if actual_content_type.lower() != expected_content_type.lower():
        raise RuntimeError(f"Static asset content type is invalid: {url}")

    cors_origin = response.headers.get("Access-Control-Allow-Origin")
    if cors_origin not in (allowed_origin, "*"):
        raise RuntimeError(f"Static asset CORS policy is invalid: {url}")

    resource_policy = response.headers.get("Cross-Origin-Resource-Policy")
    if resource_policy != "cross-origin":
        raise RuntimeError(f"Static asset resource policy is invalid: {url}")


def upload_release_manifest(
    client,
    *,
    bucket: str,
    prefix: str,
    manifest: ReleaseManifest,
) -> tuple[str, bool]:
    body = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = blake3(body).hexdigest()
    key = object_key(prefix, f"_releases/{manifest['commit']}.json")
    uploaded = True

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            IfNoneMatch="*",
            ContentType="application/json",
            CacheControl=RELEASE_CACHE_CONTROL,
            Metadata={"blake3": digest},
        )
    except ClientError as error:
        if not _is_precondition_failed(error):
            _raise_upload_error(error)
        uploaded = False

    stored = client.head_object(Bucket=bucket, Key=key)
    _validate_stored_object(
        stored,
        key=key,
        digest=digest,
        size=len(body),
        content_type="application/json",
        cache_control=RELEASE_CACHE_CONTROL,
    )
    return key, uploaded


def publish_static_assets(
    s3_client,
    http_client: httpx2.Client,
    *,
    root: Path,
    bucket: str,
    prefix: str,
    public_url: str,
    allowed_origin: str,
    commit: str,
    max_workers: int = MAX_WORKERS,
) -> ReleaseManifest:
    if not COMMIT_SHA_RE.fullmatch(commit):
        raise RuntimeError("CI_COMMIT_SHA must be a 40-character hexadecimal SHA")
    if max_workers < 1:
        raise RuntimeError("Static asset worker count must be positive")

    root = root.resolve()
    paths = collect_asset_paths(root)

    def publish(path: Path) -> UploadOutcome:
        relative = path.relative_to(root).as_posix()
        return upload_asset(
            s3_client,
            bucket=bucket,
            key=object_key(prefix, relative),
            path=path,
            relative_path=relative,
        )

    # muti-thread upload
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        outcomes = list(executor.map(publish, paths))

    def verify(outcome: UploadOutcome) -> None:
        relative = outcome.record["path"]
        check_asset(
            http_client,
            url=public_asset_url(public_url, relative),
            allowed_origin=allowed_origin,
            content_type=_content_type(root / relative),
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(verify, outcomes))

    # collect manifest
    manifest: ReleaseManifest = {
        "schema": 1,
        "commit": commit,
        "assets": [outcome.record for outcome in outcomes],
    }
    release_key, release_uploaded = upload_release_manifest(
        s3_client,
        bucket=bucket,
        prefix=prefix,
        manifest=manifest,
    )
    uploaded_count = sum(outcome.uploaded for outcome in outcomes)
    release_status = "uploaded" if release_uploaded else "existing"
    print(
        f"Static assets: {uploaded_count} uploaded, "
        f"{len(outcomes) - uploaded_count} existing"
    )
    print(f"Release manifest: {release_key} ({release_status})")
    return manifest


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Static asset configuration is missing: {name}")
    return value


def create_s3_client(
    *,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4"),
    )


def main() -> int:
    root = Path(__file__).resolve().parent.parent / "staticfiles"

    # envs
    endpoint_url = _required_environment("STATIC_ASSET_ENDPOINT_URL")
    bucket = _required_environment("STATIC_ASSET_BUCKET")
    access_key_id = _required_environment("STATIC_ASSET_ACCESS_KEY_ID")
    secret_access_key = _required_environment("STATIC_ASSET_SECRET_ACCESS_KEY")
    prefix = _required_environment("STATIC_ASSET_PREFIX")
    public_url = _required_environment("STATIC_ASSET_PUBLIC_URL")
    allowed_origin = _required_environment("STATIC_ASSET_ALLOWED_ORIGIN")
    commit = _required_environment("CI_COMMIT_SHA")

    s3_client = create_s3_client(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )
    with httpx2.Client(timeout=10) as http_client:
        publish_static_assets(
            s3_client,
            http_client,
            root=root,
            bucket=bucket,
            prefix=prefix,
            public_url=public_url,
            allowed_origin=allowed_origin,
            commit=commit,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
