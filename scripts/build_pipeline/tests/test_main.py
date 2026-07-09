import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.build_pipeline.__main__ import init, main


class CommitShaValidationTest(unittest.TestCase):
    def test_main_fails_for_invalid_commit_sha(self):
        invalid_values = (
            None,
            "",
            "a" * 39,
            "g" * 40,
            "A" * 40,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                env = {} if value is None else {"CI_COMMIT_SHA": value}
                with (
                    patch.dict(os.environ, env, clear=True),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 1)

    def test_init_accepts_valid_commit_sha(self):
        with patch.dict(os.environ, {"CI_COMMIT_SHA": "a" * 40}, clear=True):
            init()


class CleanupFailurePolicyTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "CI_COMMIT_SHA": "a" * 40,
            "REGISTRY_DOMAIN": "registry.example.com",
            "REGISTRY_CLEANUP_ENABLED": "true",
        }

    @patch(
        "scripts.build_pipeline.__main__.CleanImageTask.execute",
        side_effect=RuntimeError("cleanup failed"),
    )
    @patch("scripts.build_pipeline.__main__.Pipeline.execute")
    def test_cleanup_failure_is_ignored_when_not_required(
        self, pipeline_execute, cleanup_execute
    ):
        self.env["REGISTRY_CLEANUP_REQUIRED"] = "false"
        output = io.StringIO()

        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(output):
            result = main()

        self.assertEqual(result, 0)
        pipeline_execute.assert_called_once_with()
        cleanup_execute.assert_called_once_with()
        self.assertIn(
            "Warning: registry cleanup failed cleanup failed", output.getvalue()
        )

    @patch(
        "scripts.build_pipeline.__main__.CleanImageTask.execute",
        side_effect=RuntimeError("cleanup failed"),
    )
    @patch("scripts.build_pipeline.__main__.Pipeline.execute")
    def test_cleanup_failure_stops_pipeline_when_required(
        self, pipeline_execute, cleanup_execute
    ):
        self.env["REGISTRY_CLEANUP_REQUIRED"] = "true"

        with (
            patch.dict(os.environ, self.env, clear=True),
            redirect_stdout(io.StringIO()),
        ):
            result = main()

        self.assertEqual(result, 1)
        pipeline_execute.assert_called_once_with()
        cleanup_execute.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
