#!/usr/bin/env python

import json
import mimetypes
import os
import random
import re
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
from pathlib import Path, PurePosixPath
from threading import Lock
from time import monotonic, sleep
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
VERIFY_INITIAL_RPS = 8.0
VERIFY_MIN_RPS = 1.0
VERIFY_MAX_RPS = 32.0
VERIFY_MAX_ATTEMPTS = 8
VERIFY_SUCCESS_STEP = 50
VERIFY_MAX_BACKOFF_SECONDS = 60.0
VERIFY_USER_AGENT = "gsgfs-static-publisher/1"
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


class AdaptiveRateLimiter:
    def __init__(
        self,
        *,
        initial_rps: float,
        min_rps: float,
        max_rps: float,
        success_step: int,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ):
        rates = (initial_rps, min_rps, max_rps)
        if any(not isfinite(rate) or rate <= 0 for rate in rates):
            raise ValueError("Verification request rates must be positive and finite")
        if not min_rps <= initial_rps <= max_rps:
            raise ValueError(
                "Verification request rates must satisfy min <= initial <= max"
            )
        if type(success_step) is not int or success_step < 1:
            raise ValueError("Verification success step must be a positive integer")

        self._requests_per_second = initial_rps
        self._min_rps = min_rps
        self._max_rps = max_rps
        self._success_step = success_step
        self._success_count = 0
        self._next_request_at = 0.0
        self._blocked_until = 0.0
        self._clock = clock
        self._sleep = sleeper
        self._lock = Lock()

    @property
    def requests_per_second(self) -> float:
        with self._lock:
            return self._requests_per_second

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                ready_at = max(self._next_request_at, self._blocked_until)
                if ready_at <= now:
                    self._next_request_at = now + (1 / self._requests_per_second)
                    return
                delay = ready_at - now
            self._sleep(delay)

    def record_success(self) -> float:
        with self._lock:
            self._success_count += 1
            if self._success_count >= self._success_step:
                self._requests_per_second = min(
                    self._max_rps,
                    self._requests_per_second + 1,
                )
                self._success_count = 0
            return self._requests_per_second

    def record_throttle(self, retry_after: float) -> float:
        if not isfinite(retry_after) or retry_after < 0:
            raise ValueError("Retry delay must be non-negative and finite")

        #  exponential backoff
        with self._lock:
            now = self._clock()
            self._requests_per_second = max(
                self._min_rps,
                self._requests_per_second / 2,
            )
            self._success_count = 0
            self._blocked_until = max(
                self._blocked_until,
                now + retry_after,
            )
            self._next_request_at = max(
                self._next_request_at,
                self._blocked_until,
                now + (1 / self._requests_per_second),
            )
            return self._requests_per_second


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


def _retry_after_seconds(
    value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    if value is None:
        return None

    value = value.strip()
    try:
        seconds = int(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except TypeError, ValueError, OverflowError:
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        current_time = now or datetime.now(timezone.utc)
        return max(0.0, (retry_at - current_time).total_seconds())

    return float(seconds) if seconds >= 0 else None


def _rate_limit_retry_delay(
    response,
    *,
    attempt: int,
) -> tuple[float, str]:
    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
    if retry_after is not None:
        return retry_after, "Retry-After"

    backoff = min(VERIFY_MAX_BACKOFF_SECONDS, float(2**attempt))
    return backoff + random.uniform(0, 1), "exponential backoff"


def check_asset(
    client: httpx2.Client,
    *,
    url: str,
    allowed_origin: str,
    content_type: str,
    limiter: AdaptiveRateLimiter,
    max_attempts: int,
) -> None:
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("Verification max attempts must be a positive integer")

    headers = {
        "Origin": allowed_origin,
        "User-Agent": VERIFY_USER_AGENT,
    }
    last_cf_ray = "unknown"
    for attempt in range(max_attempts):
        limiter.acquire()
        response = client.head(url, headers=headers)
        if response.status_code != 429:
            response.raise_for_status()
            limiter.record_success()
            break

        retry_delay, delay_source = _rate_limit_retry_delay(
            response,
            attempt=attempt,
        )
        current_rps = limiter.record_throttle(retry_delay)
        last_cf_ray = response.headers.get("CF-Ray", "unknown")
        print(
            "Static asset verification rate limited: "
            f"url={url} attempt={attempt + 1}/{max_attempts} "
            f"delay={retry_delay:.2f}s source={delay_source} "
            f"rate={current_rps:.2f}rps cf_ray={last_cf_ray}",
            file=sys.stderr,
        )
    else:
        raise RuntimeError(
            "Static asset verification remained rate limited after "
            f"{max_attempts} attempts: {url} (CF-Ray: {last_cf_ray})"
        )

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
    verify_initial_rps: float = VERIFY_INITIAL_RPS,
    verify_min_rps: float = VERIFY_MIN_RPS,
    verify_max_rps: float = VERIFY_MAX_RPS,
    verify_max_attempts: int = VERIFY_MAX_ATTEMPTS,
    verify_success_step: int = VERIFY_SUCCESS_STEP,
) -> ReleaseManifest:
    if not COMMIT_SHA_RE.fullmatch(commit):
        raise RuntimeError("CI_COMMIT_SHA must be a 40-character hexadecimal SHA")
    if max_workers < 1:
        raise RuntimeError("Static asset worker count must be positive")
    if type(verify_max_attempts) is not int or verify_max_attempts < 1:
        raise RuntimeError("Static asset verification attempts must be positive")

    verify_limiter = AdaptiveRateLimiter(
        initial_rps=verify_initial_rps,
        min_rps=verify_min_rps,
        max_rps=verify_max_rps,
        success_step=verify_success_step,
    )

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
            limiter=verify_limiter,
            max_attempts=verify_max_attempts,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # consume it
        list(executor.map(verify, outcomes))
    print(
        f"Static asset verification: {len(outcomes)} checked, "
        f"final rate {verify_limiter.requests_per_second:.2f}rps"
    )

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


def _positive_float_environment(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if not isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _positive_int_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
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
    verify_initial_rps = _positive_float_environment(
        "STATIC_ASSET_VERIFY_INITIAL_RPS",
        VERIFY_INITIAL_RPS,
    )
    verify_min_rps = _positive_float_environment(
        "STATIC_ASSET_VERIFY_MIN_RPS",
        VERIFY_MIN_RPS,
    )
    verify_max_rps = _positive_float_environment(
        "STATIC_ASSET_VERIFY_MAX_RPS",
        VERIFY_MAX_RPS,
    )
    verify_max_attempts = _positive_int_environment(
        "STATIC_ASSET_VERIFY_MAX_ATTEMPTS",
        VERIFY_MAX_ATTEMPTS,
    )
    verify_success_step = _positive_int_environment(
        "STATIC_ASSET_VERIFY_SUCCESS_STEP",
        VERIFY_SUCCESS_STEP,
    )

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
            verify_initial_rps=verify_initial_rps,
            verify_min_rps=verify_min_rps,
            verify_max_rps=verify_max_rps,
            verify_max_attempts=verify_max_attempts,
            verify_success_step=verify_success_step,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
