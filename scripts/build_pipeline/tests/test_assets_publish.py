import os
import unittest
from unittest.mock import Mock, patch

from scripts.build_pipeline.task.assets_publish import (
    ENV_NAMES,
    OPTIONAL_ENV_NAMES,
    PublishStaticAssetsTask,
)


class PublishStaticAssetsTaskTest(unittest.TestCase):
    def setUp(self):
        self.runner = Mock()
        self.task = PublishStaticAssetsTask(self.runner)
        self.env = {name: f"value-for-{name.lower()}" for name in ENV_NAMES}

    def test_passes_environment_names_without_exposing_values(self):
        with patch.dict(os.environ, self.env, clear=True):
            self.task.execute()

        command = self.runner.run.call_args.args[0]
        self.assertEqual(command[:3], ["podman", "run", "--rm"])
        for name in ENV_NAMES:
            self.assertIn(
                ["--env", name],
                [command[index : index + 2] for index in range(len(command) - 1)],
            )
        self.assertEqual(
            command[-4:],
            [
                "localhost/blog-app:latest",
                "python",
                "-m",
                "scripts.publish_static_assets",
            ],
        )
        for value in self.env.values():
            self.assertNotIn(value, command)

    def test_rejects_missing_configuration(self):
        env = self.env.copy()
        del env["STATIC_ASSET_BUCKET"]

        with (
            patch.dict(os.environ, env, clear=True),
            self.assertRaisesRegex(RuntimeError, "STATIC_ASSET_BUCKET"),
        ):
            self.task.execute()

        self.runner.run.assert_not_called()

    def test_passes_configured_optional_rate_settings(self):
        env = {
            **self.env,
            "STATIC_ASSET_VERIFY_INITIAL_RPS": "12",
            "STATIC_ASSET_VERIFY_MAX_ATTEMPTS": "6",
        }

        with patch.dict(os.environ, env, clear=True):
            self.task.execute()

        command = self.runner.run.call_args.args[0]
        self.assertIn(
            ["--env", "STATIC_ASSET_VERIFY_INITIAL_RPS"],
            [command[index : index + 2] for index in range(len(command) - 1)],
        )
        self.assertIn(
            ["--env", "STATIC_ASSET_VERIFY_MAX_ATTEMPTS"],
            [command[index : index + 2] for index in range(len(command) - 1)],
        )
        for name in set(OPTIONAL_ENV_NAMES) - set(env):
            self.assertNotIn(
                ["--env", name],
                [command[index : index + 2] for index in range(len(command) - 1)],
            )


if __name__ == "__main__":
    unittest.main()
