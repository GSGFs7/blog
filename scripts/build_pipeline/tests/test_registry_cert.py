import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_pipeline.task.registry_cert import Config, SetRegistryCertTask


class RegistryCertConfigTest(unittest.TestCase):
    def test_client_certificate_and_key_must_be_provided_together(self):
        with self.assertRaisesRegex(ValueError, "must be provided together"):
            Config(
                domain="registry.example",
                ip="192.0.2.1",
                ca_cert="",
                client_cert="certificate",
                client_key="",
            )


class SetRegistryCertTaskTest(unittest.TestCase):
    def test_writes_separate_podman_and_curl_ca_files(self):
        config = Config(
            domain="registry.example",
            ip="192.0.2.1",
            ca_cert="CUSTOM CA",
            client_cert="CLIENT CERT",
            client_key="CLIENT KEY",
        )

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            system_ca = home / "system-ca.crt"
            system_ca.write_text("SYSTEM CA", encoding="utf-8")

            with patch(
                "scripts.build_pipeline.task.registry_cert.Path.home",
                return_value=home,
            ):
                SetRegistryCertTask(config, (system_ca,)).execute()

                cert_dir = config.cert_dir
                self.assertEqual(
                    (cert_dir / "ca.crt").read_text(encoding="utf-8"),
                    "CUSTOM CA\n",
                )
                self.assertEqual(
                    config.curl_ca_bundle.read_text(encoding="utf-8"),
                    "SYSTEM CA\nCUSTOM CA\n",
                )
                self.assertEqual(
                    (cert_dir / "client.cert").read_text(encoding="utf-8"),
                    "CLIENT CERT\n",
                )
                self.assertEqual(
                    (cert_dir / "client.key").read_text(encoding="utf-8"),
                    "CLIENT KEY\n",
                )
                key_mode = stat.S_IMODE((cert_dir / "client.key").stat().st_mode)
                self.assertEqual(key_mode, 0o600)

    def test_uses_system_ca_for_curl_without_creating_podman_ca(self):
        config = Config(
            domain="registry.example",
            ip="192.0.2.1",
            ca_cert="",
            client_cert="",
            client_key="",
        )

        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            system_ca = home / "system-ca.crt"
            system_ca.write_text("SYSTEM CA\n", encoding="utf-8")

            with patch(
                "scripts.build_pipeline.task.registry_cert.Path.home",
                return_value=home,
            ):
                SetRegistryCertTask(config, (system_ca,)).execute()

                self.assertFalse((config.cert_dir / "ca.crt").exists())
                self.assertEqual(
                    config.curl_ca_bundle.read_text(encoding="utf-8"),
                    "SYSTEM CA\n",
                )


if __name__ == "__main__":
    unittest.main()
