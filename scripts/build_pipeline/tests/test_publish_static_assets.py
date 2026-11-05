import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import Mock, patch

from core.r2 import ObjectMetadata, PreconditionFailed, SignatureMismatch
from scripts.publish_static_assets import (
    IMMUTABLE_CACHE_CONTROL,
    VERIFY_USER_AGENT,
    AdaptiveRateLimiter,
    _content_type,
    _positive_float_environment,
    _positive_int_environment,
    _required_environment,
    _retry_after_seconds,
    check_asset,
    collect_asset_paths,
    main,
    object_key,
    public_asset_url,
    publish_static_assets,
    upload_asset,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class FakeR2Client:
    def __init__(self):
        self.objects = {}

    def put(self, key, body, **kwargs):
        if kwargs["if_none_match"] == "*" and key in self.objects:
            raise PreconditionFailed("Object already exists", status_code=412)

        data = body.read() if hasattr(body, "read") else body
        if "content_length" in kwargs:
            assert kwargs["content_length"] == len(data)
        self.objects[key] = {
            "body": data,
            "metadata": kwargs["metadata"],
            "content_type": kwargs["content_type"],
            "cache_control": kwargs["cache_control"],
        }

    def stat(self, key):
        stored = self.objects[key]
        return ObjectMetadata(
            key=key,
            metadata=stored["metadata"],
            size=len(stored["body"]),
            content_type=stored["content_type"],
            cache_control=stored["cache_control"],
        )


class AdaptiveRateLimiterTest(unittest.TestCase):
    def test_paces_requests_and_adapts_rate(self):
        clock = FakeClock()
        limiter = AdaptiveRateLimiter(
            initial_rps=2,
            min_rps=1,
            max_rps=4,
            success_step=2,
            clock=clock,
            sleeper=clock.sleep,
        )

        limiter.acquire()
        limiter.acquire()
        self.assertEqual(clock.sleeps, [0.5])

        limiter.record_success()
        self.assertEqual(limiter.record_success(), 3)

        self.assertEqual(limiter.record_throttle(3), 1.5)
        limiter.acquire()
        self.assertEqual(clock.sleeps, [0.5, 3])

    def test_rejects_invalid_configuration(self):
        invalid_configurations = [
            {
                "initial_rps": 0,
                "min_rps": 1,
                "max_rps": 4,
                "success_step": 2,
            },
            {
                "initial_rps": 2,
                "min_rps": 3,
                "max_rps": 4,
                "success_step": 2,
            },
            {
                "initial_rps": 2,
                "min_rps": 1,
                "max_rps": 4,
                "success_step": 0,
            },
        ]

        for configuration in invalid_configurations:
            with self.subTest(configuration=configuration):
                with self.assertRaises(ValueError):
                    AdaptiveRateLimiter(**configuration)

    def test_keeps_rate_within_configured_bounds(self):
        limiter = AdaptiveRateLimiter(
            initial_rps=2,
            min_rps=1,
            max_rps=3,
            success_step=1,
        )

        for _ in range(10):
            limiter.record_success()
        self.assertEqual(limiter.requests_per_second, 3)

        for _ in range(10):
            limiter.record_throttle(0)
        self.assertEqual(limiter.requests_per_second, 1)


class StaticAssetRetryTest(unittest.TestCase):
    def valid_response(self):
        response = Mock()
        response.status_code = 200
        response.headers = {
            "Cache-Control": IMMUTABLE_CACHE_CONTROL,
            "Content-Type": "text/css",
            "Access-Control-Allow-Origin": "https://gsgfs.moe",
            "Cross-Origin-Resource-Policy": "cross-origin",
        }
        return response

    def check(self, client, limiter, *, max_attempts=3):
        check_asset(
            client,
            url="https://static.gsgfs.moe/static/asset.css",
            allowed_origin="https://gsgfs.moe",
            content_type="text/css",
            limiter=limiter,
            max_attempts=max_attempts,
        )

    def test_parses_retry_after_seconds_and_http_date(self):
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        retry_at = format_datetime(now + timedelta(seconds=30), usegmt=True)

        self.assertEqual(_retry_after_seconds("12", now=now), 12)
        self.assertEqual(_retry_after_seconds(retry_at, now=now), 30)
        self.assertIsNone(_retry_after_seconds("-1", now=now))
        self.assertIsNone(_retry_after_seconds("invalid", now=now))

    def test_retries_429_with_shared_retry_after(self):
        limited = Mock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "3", "CF-Ray": "test-ray"}
        client = Mock()
        client.head.side_effect = [limited, self.valid_response()]
        limiter = Mock(spec=AdaptiveRateLimiter)
        limiter.record_throttle.return_value = 4

        self.check(client, limiter)

        self.assertEqual(limiter.acquire.call_count, 2)
        limiter.record_throttle.assert_called_once_with(3)
        limiter.record_success.assert_called_once_with()
        client.head.assert_called_with(
            "https://static.gsgfs.moe/static/asset.css",
            headers={
                "Origin": "https://gsgfs.moe",
                "User-Agent": VERIFY_USER_AGENT,
            },
        )

    @patch("scripts.publish_static_assets.random.uniform", return_value=0.25)
    def test_uses_exponential_backoff_without_retry_after(self, uniform):
        limited = Mock()
        limited.status_code = 429
        limited.headers = {}
        client = Mock()
        client.head.side_effect = [limited, self.valid_response()]
        limiter = Mock(spec=AdaptiveRateLimiter)
        limiter.record_throttle.return_value = 4

        self.check(client, limiter)

        limiter.record_throttle.assert_called_once_with(1.25)
        uniform.assert_called_once_with(0, 1)

    def test_fails_after_rate_limit_retry_budget(self):
        limited = Mock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "0", "CF-Ray": "test-ray"}
        client = Mock()
        client.head.return_value = limited
        limiter = Mock(spec=AdaptiveRateLimiter)
        limiter.record_throttle.return_value = 1

        with self.assertRaisesRegex(RuntimeError, "test-ray"):
            self.check(client, limiter, max_attempts=2)

        self.assertEqual(limiter.acquire.call_count, 2)
        self.assertEqual(limiter.record_throttle.call_count, 2)
        limiter.record_success.assert_not_called()


class StaticAssetSelectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "dist").mkdir()
        (self.root / "admin").mkdir()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_manifests(self):
        (self.root / "staticfiles.json").write_text(
            json.dumps(
                {
                    "paths": {
                        "admin/base.css": "admin/base.abc.css",
                        "source.js.map": "source.abc.js.map",
                        "ssr/ssr.mjs": "ssr/ssr.abc.mjs",
                        "ssr/solid-islands.json": "ssr/solid-islands.abc.json",
                        "ssr/solid-hydrate-script.js": (
                            "ssr/solid-hydrate-script.abc.js"
                        ),
                        "dist/manifest.json": "dist/manifest.abc.json",
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.root / "dist" / "manifest.json").write_text(
            json.dumps(
                {
                    "entry.ts": {
                        "file": "entry-abc.js",
                        "css": ["entry-def.css"],
                        "assets": ["font-ghi.woff2"],
                    },
                    "_chunk.js": {"file": "chunk-jkl.js"},
                }
            ),
            encoding="utf-8",
        )

    def test_collects_hashed_django_and_vite_assets(self):
        self.write_manifests()
        expected = {
            "admin/base.abc.css",
            "dist/chunk-jkl.js",
            "dist/entry-abc.js",
            "dist/entry-def.css",
            "dist/font-ghi.woff2",
            "ssr/solid-hydrate-script.abc.js",
        }
        for relative in expected:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode())

        actual = {
            path.relative_to(self.root).as_posix()
            for path in collect_asset_paths(self.root)
        }

        self.assertEqual(actual, expected)

    def test_rejects_missing_selected_asset(self):
        self.write_manifests()

        with self.assertRaisesRegex(RuntimeError, "admin/base.abc.css"):
            collect_asset_paths(self.root)


class StaticAssetMimeTypeTest(unittest.TestCase):
    def test_supports_current_static_file_types(self):
        expected = {
            ".asc": "application/pgp-signature",
            ".css": "text/css",
            ".ico": "image/vnd.microsoft.icon",
            ".js": "text/javascript",
            ".md": "text/markdown",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ttf": "font/ttf",
            ".txt": "text/plain",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }

        for suffix, content_type in expected.items():
            with self.subTest(suffix=suffix):
                self.assertEqual(_content_type(f"asset{suffix}"), content_type)

        self.assertEqual(
            _content_type("asset.unknown-static-type"),
            "application/octet-stream",
        )


class StaticAssetLocationTest(unittest.TestCase):
    def test_normalizes_object_key_and_public_url(self):
        self.assertEqual(
            object_key("/static/", "dist/entry file.js"),
            "static/dist/entry file.js",
        )
        self.assertEqual(
            public_asset_url(
                "https://static.gsgfs.moe/static/",
                "dist/entry file.js",
            ),
            "https://static.gsgfs.moe/static/dist/entry%20file.js",
        )

    def test_rejects_invalid_paths_and_public_url(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid static asset path"):
            object_key("static", "../secret")
        with self.assertRaisesRegex(RuntimeError, "public URL"):
            public_asset_url("static/", "dist/entry.js")


class StaticAssetConfigurationTest(unittest.TestCase):
    @patch("scripts.publish_static_assets.publish_static_assets")
    @patch("scripts.publish_static_assets.httpx2.Client")
    @patch("scripts.publish_static_assets.SyncR2Client")
    def test_main_configures_and_closes_clients(self, r2_client, http_client, publish):
        environment = {
            "STATIC_ASSET_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
            "STATIC_ASSET_ACCESS_KEY_ID": "access-key",
            "STATIC_ASSET_SECRET_ACCESS_KEY": "secret-key",
            "STATIC_ASSET_BUCKET": "static-bucket",
            "STATIC_ASSET_PREFIX": "static",
            "STATIC_ASSET_PUBLIC_URL": "https://static.example.com",
            "STATIC_ASSET_ALLOWED_ORIGIN": "https://example.com",
            "CI_COMMIT_SHA": "a" * 40,
        }
        for error in (None, RuntimeError("publish failed")):
            with self.subTest(error=error):
                r2_client.reset_mock()
                http_client.reset_mock()
                publish.side_effect = error
                with patch.dict("os.environ", environment, clear=True):
                    if error is None:
                        self.assertEqual(main(), 0)
                    else:
                        with self.assertRaisesRegex(RuntimeError, "publish failed"):
                            main()
                r2_client.assert_called_once_with(
                    endpoint=environment["STATIC_ASSET_ENDPOINT_URL"],
                    access_key="access-key",
                    secret_key="secret-key",
                    bucket="static-bucket",
                )
                self.assertEqual(
                    publish.call_args.args,
                    (
                        r2_client.return_value.__enter__.return_value,
                        http_client.return_value.__enter__.return_value,
                    ),
                )
                r2_client.return_value.__exit__.assert_called_once()
                http_client.return_value.__exit__.assert_called_once()

    @patch(
        "scripts.publish_static_assets.os.getenv",
        return_value="  secret-value\n",
    )
    def test_strips_environment_whitespace(self, getenv):
        self.assertEqual(
            _required_environment("STATIC_ASSET_SECRET_ACCESS_KEY"),
            "secret-value",
        )
        getenv.assert_called_once_with("STATIC_ASSET_SECRET_ACCESS_KEY", "")

    def test_reads_optional_rate_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "STATIC_ASSET_VERIFY_INITIAL_RPS": " 12.5 ",
                "STATIC_ASSET_VERIFY_MAX_ATTEMPTS": " 6 ",
            },
            clear=True,
        ):
            self.assertEqual(
                _positive_float_environment(
                    "STATIC_ASSET_VERIFY_INITIAL_RPS",
                    8,
                ),
                12.5,
            )
            self.assertEqual(
                _positive_int_environment(
                    "STATIC_ASSET_VERIFY_MAX_ATTEMPTS",
                    8,
                ),
                6,
            )
            self.assertEqual(
                _positive_float_environment(
                    "STATIC_ASSET_VERIFY_MIN_RPS",
                    1,
                ),
                1,
            )

    def test_rejects_invalid_rate_configuration(self):
        invalid_values = ("", "0", "-1", "nan", "invalid")

        for value in invalid_values:
            with self.subTest(value=value):
                with patch.dict(
                    "os.environ",
                    {"STATIC_ASSET_VERIFY_INITIAL_RPS": value},
                    clear=True,
                ):
                    with self.assertRaisesRegex(RuntimeError, "positive number"):
                        _positive_float_environment(
                            "STATIC_ASSET_VERIFY_INITIAL_RPS",
                            8,
                        )

        for value in ("", "0", "-1", "1.5", "invalid"):
            with self.subTest(integer_value=value):
                with patch.dict(
                    "os.environ",
                    {"STATIC_ASSET_VERIFY_MAX_ATTEMPTS": value},
                    clear=True,
                ):
                    with self.assertRaisesRegex(RuntimeError, "positive integer"):
                        _positive_int_environment(
                            "STATIC_ASSET_VERIFY_MAX_ATTEMPTS",
                            8,
                        )


class StaticAssetPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "dist").mkdir()
        (self.root / "asset.abc.css").write_text("body {}", encoding="utf-8")
        (self.root / "staticfiles.json").write_text(
            json.dumps({"paths": {"asset.css": "asset.abc.css"}}),
            encoding="utf-8",
        )
        (self.root / "dist" / "manifest.json").write_text("{}", encoding="utf-8")
        self.s3_client = FakeR2Client()
        self.http_client = Mock()
        response = Mock()
        response.status_code = 200
        response.headers = {
            "Cache-Control": IMMUTABLE_CACHE_CONTROL,
            "Content-Type": "text/css",
            "Access-Control-Allow-Origin": "https://gsgfs.moe",
            "Cross-Origin-Resource-Policy": "cross-origin",
        }
        self.http_client.head.return_value = response

    def tearDown(self):
        self.temporary_directory.cleanup()

    def publish(self, **kwargs):
        return publish_static_assets(
            self.s3_client,
            self.http_client,
            root=self.root,
            prefix="/static/",
            public_url="https://static.gsgfs.moe/static/",
            allowed_origin="https://gsgfs.moe",
            commit="a" * 40,
            max_workers=1,
            **kwargs,
        )

    def test_publication_is_idempotent_and_uses_relative_paths(self):
        first = self.publish()
        second = self.publish()

        expected_record = {
            "path": "asset.abc.css",
            "blake3": first["assets"][0]["blake3"],
            "size": 7,
        }
        self.assertEqual(first["assets"], [expected_record])
        self.assertEqual(second["assets"], [expected_record])
        self.assertNotIn(None, second["assets"])
        self.assertEqual(
            set(self.s3_client.objects),
            {
                "static/asset.abc.css",
                f"static/_releases/{'a' * 40}.json",
            },
        )

        release = json.loads(
            self.s3_client.objects[f"static/_releases/{'a' * 40}.json"]["body"]
        )
        self.assertEqual(release["assets"], [expected_record])
        self.assertEqual(
            self.s3_client.objects[f"static/_releases/{'a' * 40}.json"][
                "cache_control"
            ],
            "no-store",
        )
        self.http_client.head.assert_called_with(
            "https://static.gsgfs.moe/static/asset.abc.css",
            headers={
                "Origin": "https://gsgfs.moe",
                "User-Agent": VERIFY_USER_AGENT,
            },
        )

    def test_rejects_existing_object_with_different_content(self):
        path = self.root / "asset.abc.css"
        upload_asset(
            self.s3_client,
            key="static/asset.abc.css",
            path=path,
            relative_path="asset.abc.css",
        )
        path.write_text("different", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "collision"):
            upload_asset(
                self.s3_client,
                key="static/asset.abc.css",
                path=path,
                relative_path="asset.abc.css",
            )

    def test_reports_signature_configuration_error(self):
        self.s3_client.put = Mock(
            side_effect=SignatureMismatch("SignatureDoesNotMatch", status_code=403)
        )

        with self.assertRaisesRegex(RuntimeError, "R2 rejected the S3 signature"):
            self.publish()

    def test_reports_expected_and_stored_size_without_publishing_release(self):
        self.publish()
        release_key = f"static/_releases/{'a' * 40}.json"
        del self.s3_client.objects[release_key]
        stored = self.s3_client.stat("static/asset.abc.css")

        for size in (None, 3):
            with self.subTest(size=size):
                self.s3_client.stat = Mock(
                    return_value=ObjectMetadata(
                        key=stored.key,
                        metadata=stored.metadata,
                        size=size,
                        content_type=stored.content_type,
                        cache_control=stored.cache_control,
                        content_encoding="gzip",
                    )
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    f"expected=7, stored={size}, content_encoding='gzip'",
                ):
                    self.publish()
                self.assertNotIn(release_key, self.s3_client.objects)

    def test_does_not_publish_release_when_public_check_fails(self):
        self.http_client.head.return_value.raise_for_status.side_effect = RuntimeError(
            "unavailable"
        )

        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.publish()

        self.assertIn("static/asset.abc.css", self.s3_client.objects)
        self.assertNotIn(
            f"static/_releases/{'a' * 40}.json",
            self.s3_client.objects,
        )

    def test_does_not_publish_release_when_rate_limit_persists(self):
        response = Mock()
        response.status_code = 429
        response.headers = {"Retry-After": "0", "CF-Ray": "test-ray"}
        self.http_client.head.return_value = response

        with self.assertRaisesRegex(RuntimeError, "test-ray"):
            self.publish(verify_max_attempts=1)

        self.assertIn("static/asset.abc.css", self.s3_client.objects)
        self.assertNotIn(
            f"static/_releases/{'a' * 40}.json",
            self.s3_client.objects,
        )


if __name__ == "__main__":
    unittest.main()
