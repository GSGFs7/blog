import os
from dataclasses import dataclass
from pathlib import Path

from ..type import Task


@dataclass(frozen=True, slots=True)
class Config:
    domain: str
    ip: str | None
    ca_cert: str
    client_cert: str
    client_key: str

    @staticmethod
    def for_env() -> "Config":
        return Config(
            domain=os.getenv("REGISTRY_DOMAIN", ""),
            ip=os.getenv("REGISTRY_IP"),
            ca_cert=os.getenv("REGISTRY_CA_CERT", ""),
            client_cert=os.getenv("REGISTRY_CLIENT_CERT", ""),
            client_key=os.getenv("REGISTRY_CLIENT_KEY", ""),
        )

    @property
    def cert_dir(self) -> Path:
        return Path.home() / ".config" / "containers" / "certs.d" / self.domain

    def __post_init__(self):
        def _verify_str(value: str):
            """is str & non-empty"""
            return not isinstance(value, str) or not value

        if _verify_str(self.domain):
            raise ValueError("REGISTRY_DOMAIN environment variable is missing or empty")
        if self.ip is not None and _verify_str(self.ip):
            raise ValueError("REGISTRY_IP must be a non-empty string or None")


class SetRegistryCertTask(Task):
    def __init__(self, config: Config | None = None):
        if config is None:
            config = Config.for_env()
        self.config = config

    def execute(self) -> None:
        base_dir = self.config.cert_dir
        base_dir.mkdir(parents=True, exist_ok=True)

        # write
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        for file_name, content in (
            ("ca.crt", self.config.ca_cert),
            ("client.cert", self.config.client_cert),
            ("client.key", self.config.client_key),
        ):
            dest_path = base_dir / file_name

            # if not content. don't create this file
            if not content:
                dest_path.unlink(missing_ok=True)
                continue

            fd = os.open(dest_path, flags=flags, mode=mode)
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)

        # add system ca
        ca_bundles = (
            "/etc/ssl/certs/ca-certificates.crt",
            "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/ssl/ca-bundle.pem",
            "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
        )
        for ca in ca_bundles:
            try:
                with open(ca, "r") as source:
                    with open(base_dir / "ca.crt", "a") as target:
                        target.write(source.read())
                        return
            except Exception:
                pass

        if (base_dir / "ca.crt").exists():
            print("Warning: Custom CA only; no system CA bundle found.")
            return

        raise ValueError("No valid system CA bundle or custom CA found.")
