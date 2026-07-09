import subprocess
import unittest
from unittest.mock import Mock, call

from scripts.build_pipeline.task.registry_cert import Config
from scripts.build_pipeline.task.registry_check import CheckRegistryRouteTask


class CheckRegistryRouteTaskTest(unittest.TestCase):
    def setUp(self):
        self.runner = Mock()
        self.config = Config(
            domain="registry.example",
            ip="192.0.2.1",
            ca_cert="",
            client_cert="",
            client_key="",
        )
        self.task = CheckRegistryRouteTask(self.runner, self.config)

    def completed_process(
        self,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_accepts_expected_route_and_registry_connection(self):
        self.runner.run.side_effect = (
            self.completed_process(
                0,
                "192.0.2.1 STREAM registry.example\n::1 STREAM registry.example\n",
            ),
            self.completed_process(0),
        )

        self.task.execute()

        self.assertEqual(
            self.runner.run.call_args_list,
            [
                call(
                    ["getent", "ahosts", "registry.example"],
                    capture=True,
                ),
                call(
                    [
                        "skopeo",
                        "inspect",
                        "docker://registry.example/blog-app:latest",
                    ],
                    capture=True,
                    check=False,
                ),
            ],
        )

    def test_rejects_unexpected_resolved_address(self):
        self.runner.run.return_value = self.completed_process(
            0,
            "192.0.2.1 STREAM registry.example\n198.51.100.2 STREAM registry.example\n",
        )

        with self.assertRaisesRegex(RuntimeError, "198.51.100.2"):
            self.task.execute()

        self.runner.run.assert_called_once()

    def test_accepts_missing_probe_image_as_successful_connection(self):
        self.runner.run.side_effect = (
            self.completed_process(0, "192.0.2.1 STREAM registry.example\n"),
            self.completed_process(1, stderr="manifest unknown"),
        )

        self.task.execute()

    def test_propagates_registry_connection_failure(self):
        self.runner.run.side_effect = (
            self.completed_process(0, "192.0.2.1 STREAM registry.example\n"),
            self.completed_process(1, stderr="certificate verify failed"),
        )

        with self.assertRaisesRegex(RuntimeError, "certificate verify failed"):
            self.task.execute()


if __name__ == "__main__":
    unittest.main()
