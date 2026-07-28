import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from scripts.publish_static_assets import (
    IMMUTABLE_CACHE_CONTROL,
    S3_REGION,
    _content_type,
    _required_environment,
    collect_asset_paths,
    create_s3_client,
    object_key,
    public_asset_url,
    publish_static_assets,
    upload_asset,
)


class FakeS3Client:
    def __init__(self):
        self.objects = {}

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "PreconditionFailed"},
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )

        body = kwargs["Body"]
        data = body.read() if hasattr(body, "read") else body
        self.objects[key] = {
            "body": data,
            "metadata": kwargs["Metadata"],
            "content_type": kwargs["ContentType"],
            "cache_control": kwargs["CacheControl"],
        }

    def head_object(self, *, Bucket, Key):
        del Bucket
        stored = self.objects[Key]
        return {
            "Metadata": stored["metadata"],
            "ContentLength": len(stored["body"]),
            "ContentType": stored["content_type"],
            "CacheControl": stored["cache_control"],
        }


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
    @patch("scripts.publish_static_assets.boto3.client")
    def test_uses_r2_signature_configuration(self, boto_client):
        expected_client = Mock()
        boto_client.return_value = expected_client

        actual = create_s3_client(
            endpoint_url="https://account.r2.cloudflarestorage.com",
            access_key_id="access-key",
            secret_access_key="secret-key",
        )

        self.assertIs(actual, expected_client)
        boto_client.assert_called_once()
        args, kwargs = boto_client.call_args
        self.assertEqual(args, ("s3",))
        self.assertEqual(kwargs["region_name"], S3_REGION)
        self.assertEqual(kwargs["config"].signature_version, "s3v4")

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
        self.s3_client = FakeS3Client()
        self.http_client = Mock()
        response = Mock()
        response.headers = {
            "Cache-Control": IMMUTABLE_CACHE_CONTROL,
            "Content-Type": "text/css",
            "Access-Control-Allow-Origin": "https://gsgfs.moe",
            "Cross-Origin-Resource-Policy": "cross-origin",
        }
        self.http_client.head.return_value = response

    def tearDown(self):
        self.temporary_directory.cleanup()

    def publish(self):
        return publish_static_assets(
            self.s3_client,
            self.http_client,
            root=self.root,
            bucket="static-bucket",
            prefix="/static/",
            public_url="https://static.gsgfs.moe/static/",
            allowed_origin="https://gsgfs.moe",
            commit="a" * 40,
            max_workers=1,
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
            headers={"Origin": "https://gsgfs.moe"},
        )

    def test_rejects_existing_object_with_different_content(self):
        path = self.root / "asset.abc.css"
        upload_asset(
            self.s3_client,
            bucket="static-bucket",
            key="static/asset.abc.css",
            path=path,
            relative_path="asset.abc.css",
        )
        path.write_text("different", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "collision"):
            upload_asset(
                self.s3_client,
                bucket="static-bucket",
                key="static/asset.abc.css",
                path=path,
                relative_path="asset.abc.css",
            )

    def test_reports_signature_configuration_error(self):
        self.s3_client.put_object = Mock(
            side_effect=ClientError(
                {
                    "Error": {"Code": "SignatureDoesNotMatch"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "PutObject",
            )
        )

        with self.assertRaisesRegex(RuntimeError, "R2 rejected the S3 signature"):
            self.publish()

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


if __name__ == "__main__":
    unittest.main()
