import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..type import Task

SYSTEM_CA_BUNDLES = (
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
    Path("/etc/ssl/ca-bundle.pem"),
    Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"),
)


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

    @property
    def curl_ca_bundle(self) -> Path:
        return self.cert_dir / "curl-ca-bundle.pem"

    def __post_init__(self):
        def _verify_str(value: str):
            """is str & non-empty"""
            return not isinstance(value, str) or not value

        if _verify_str(self.domain):
            raise ValueError("REGISTRY_DOMAIN environment variable is missing or empty")
        if self.ip is not None and _verify_str(self.ip):
            raise ValueError("REGISTRY_IP must be a non-empty string or None")
        if bool(self.client_cert) != bool(self.client_key):
            raise ValueError(
                "REGISTRY_CLIENT_CERT and REGISTRY_CLIENT_KEY must be provided together"
            )


class SetRegistryCertTask(Task):
    def __init__(
        self,
        config: Config | None = None,
        ca_bundles: Sequence[Path] = SYSTEM_CA_BUNDLES,
    ):
        if config is None:
            config = Config.for_env()
        self.config = config
        self.ca_bundles = ca_bundles

    def write_file(self, path: Path, content: str) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(path, flags=flags, mode=mode)
        with open(fd, "w", encoding="utf-8") as file:
            file.write(content.rstrip("\r\n") + "\n")
        path.chmod(mode)

    def find_system_ca_bundle(self) -> str | None:
        for path in self.ca_bundles:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if content.strip():
                return content
        return None

    def execute(self) -> None:
        base_dir = self.config.cert_dir
        base_dir.mkdir(parents=True, exist_ok=True)

        for file_name, content in (
            ("ca.crt", self.config.ca_cert),
            ("client.cert", self.config.client_cert),
            ("client.key", self.config.client_key),
        ):
            dest_path = base_dir / file_name
            if not content:
                dest_path.unlink(missing_ok=True)
                continue
            self.write_file(dest_path, content)

        system_ca = self.find_system_ca_bundle()
        if system_ca is None and not self.config.ca_cert:
            raise ValueError("No valid system CA bundle or custom CA found.")
        if system_ca is None:
            print("Warning: Custom CA only; no system CA bundle found.")

        curl_ca_parts = [part for part in (system_ca, self.config.ca_cert) if part]
        self.write_file(self.config.curl_ca_bundle, "\n".join(curl_ca_parts))
