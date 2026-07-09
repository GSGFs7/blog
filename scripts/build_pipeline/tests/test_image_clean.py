import os
import subprocess
import unittest
from unittest.mock import Mock, patch

from scripts.build_pipeline.task.image_clean import CleanImageTask
from scripts.build_pipeline.task.registry_cert import Config


class CleanImageTaskTest(unittest.TestCase):
    def setUp(self):
        self.runner = Mock()
        self.task = CleanImageTask(
            self.runner,
            (("blog-app", "Containerfile", None),),
            Config(
                domain="registry.example",
                ip=None,
                ca_cert="",
                client_cert="",
                client_key="",
            ),
        )

    def test_get_image_tags_propagates_registry_failure(self):
        with patch.object(self.task, "curl", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                self.task.get_image_tags("blog-app")

    def test_get_image_tags_rejects_invalid_response(self):
        with patch.object(self.task, "curl", return_value='{"tags": "latest"}'):
            with self.assertRaisesRegex(ValueError, "Invalid tags response"):
                self.task.get_image_tags("blog-app")

    def test_get_image_tags_accepts_repository_without_tags(self):
        with patch.object(self.task, "curl", return_value='{"tags": null}'):
            self.assertEqual(self.task.get_image_tags("blog-app"), [])

    def test_curl_uses_combined_ca_bundle(self):
        self.runner.run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout="response",
            stderr="",
        )

        self.assertEqual(self.task.curl("/v2/"), "response")

        args = self.runner.run.call_args.args[0]
        ca_index = args.index("--cacert")
        self.assertEqual(args[ca_index + 1], str(self.task.config.curl_ca_bundle))

    def test_execute_propagates_digest_failure(self):
        stale_tag = "a" * 40
        with (
            patch.object(self.task, "collect_keep_tags", return_value={"latest"}),
            patch.object(self.task, "get_image_tags", return_value=[stale_tag]),
            patch.object(
                self.task,
                "get_manifest_digest",
                side_effect=RuntimeError("digest failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "digest failed"):
                self.task.execute()

    def test_execute_propagates_delete_failure(self):
        stale_tag = "a" * 40
        with (
            patch.dict(os.environ, {"REGISTRY_CLEANUP_DRY_RUN": "false"}),
            patch.object(self.task, "collect_keep_tags", return_value={"latest"}),
            patch.object(self.task, "get_image_tags", return_value=[stale_tag]),
            patch.object(
                self.task,
                "get_manifest_digest",
                return_value="sha256:digest",
            ),
            patch.object(
                self.task,
                "delete_image_digest",
                side_effect=RuntimeError("delete failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "delete failed"):
                self.task.execute()


if __name__ == "__main__":
    unittest.main()
