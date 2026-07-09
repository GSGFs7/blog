import re

from ..type import Runner, Task
from .registry_cert import Config

MISSING_IMAGE_RE = re.compile(r"manifest unknown|name unknown", re.IGNORECASE)
LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}


class CheckRegistryRouteTask(Task):
    def __init__(
        self,
        runner: Runner,
        config: Config | None = None,
        probe_image: str = "blog-app",
    ):
        self.runner = runner
        self.config = config if config is not None else Config.for_env()
        self.probe_image = probe_image

    def resolve_addresses(self) -> set[str]:
        if self.config.ip is None:
            raise ValueError("REGISTRY_IP environment variable is missing")

        # e.g.: 2a00:1450:*:*::* google.com
        output = self.runner.run(
            ["getent", "ahosts", self.config.domain],
            capture=True,
        ).stdout
        addresses = {
            line.split(maxsplit=1)[0] for line in output.splitlines() if line.strip()
        }
        if not addresses:
            raise RuntimeError(f"Could not resolve {self.config.domain}")
        if self.config.ip not in addresses:
            raise RuntimeError(
                f"Expected {self.config.domain} to resolve to {self.config.ip}"
            )

        # check DNS leak
        unexpected = addresses - {self.config.ip} - LOOPBACK_ADDRESSES
        if unexpected:
            values = ", ".join(sorted(unexpected))
            raise RuntimeError(
                f"Unexpected addresses for {self.config.domain}: {values}"
            )
        return addresses

    def check_registry_connection(self) -> None:
        image = f"docker://{self.config.domain}/{self.probe_image}:latest"
        result = self.runner.run(
            ["skopeo", "inspect", image],
            capture=True,
            check=False,
        )
        if result.returncode == 0:
            return

        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if MISSING_IMAGE_RE.search(output):
            return
        raise RuntimeError(
            "Skopeo could not connect to registry "
            f"{self.config.domain}: {output.strip()}"
        )

    def execute(self) -> None:
        addresses = self.resolve_addresses()
        if "::1" not in addresses:
            print("Warning: Registry IPv6 blackhole (::1) is not configured.")
        self.check_registry_connection()
