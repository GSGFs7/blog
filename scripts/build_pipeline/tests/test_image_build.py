import os
import unittest
from unittest.mock import Mock, patch

from scripts.build_pipeline.task.image_build import BuildImageTask


class BuildImageTaskTest(unittest.TestCase):
    def setUp(self):
        self.runner = Mock()

    def test_app_image_receives_commit_build_id(self):
        task = BuildImageTask(
            self.runner,
            (("blog-app", "app.Dockerfile", None),),
        )

        with patch.dict(os.environ, {"CI_COMMIT_SHA": "a" * 40}, clear=True):
            task.execute()

        self.runner.run.assert_called_once_with(
            [
                "podman",
                "build",
                "-f",
                "app.Dockerfile",
                "--build-arg",
                f"BUILD_ID={'a' * 40}",
                "-t",
                "localhost/blog-app:latest",
                ".",
            ]
        )

    def test_non_app_image_does_not_receive_build_id(self):
        task = BuildImageTask(
            self.runner,
            (("blog-backup", "backup.Dockerfile", "runtime"),),
        )

        with patch.dict(os.environ, {}, clear=True):
            task.execute()

        self.runner.run.assert_called_once_with(
            [
                "podman",
                "build",
                "-f",
                "backup.Dockerfile",
                "-t",
                "localhost/blog-backup:latest",
                "--target",
                "runtime",
                ".",
            ]
        )


if __name__ == "__main__":
    unittest.main()
