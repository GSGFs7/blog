import json
import os
import re
from pathlib import Path
from typing import TypedDict

from .cert import Config
from .image_base import BaseImageTask

MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
COMMIT_TAG_RE = re.compile(r"^[0-9a-f]{40}$")


class TagResponse(TypedDict):
    name: str
    tags: list[str]


class CleanImageTask(BaseImageTask):
    def __init__(self, runner, images, config: Config | None = None):
        super().__init__(runner, images)
        if config is None:
            self.config = Config.for_env()
        else:
            self.config = config

    def collect_keep_tags(self) -> set[str]:
        keep_tags = {"latest"}

        # from git history
        output = self.runner.run(
            ["git", "rev-list", "--max-count=2", "HEAD"],
            capture=True,
        ).stdout
        for line in output.splitlines():
            line = line.strip()
            if line:
                keep_tags.add(line)

        # from env (new)
        commit_hash = os.getenv("CI_COMMIT_SHA", "")
        if commit_hash and commit_hash not in keep_tags:
            keep_tags.add(commit_hash)

        # from k8s config (now running image)
        lines = (
            Path(".config/k8s/overlays/prod/kustomization.yaml").read_text().split("\n")
        )
        for line in lines:
            if "newTag" in line:
                tag = line.split(":", 1)[-1].strip().strip("\"'")
                if COMMIT_TAG_RE.match(tag) and tag not in keep_tags:
                    keep_tags.add(tag)
        return keep_tags

    def curl(self, path: str, *args: str, check: bool = True) -> str:
        # fmt: off
        cmd = [
            "curl",
            "-fsS",
            "--noproxy", self.config.domain,
            "--retry", "3",
            "--retry-delay", "3",
            *args
        ]
        # fmt: on

        cert_dir = self.config.cert_dir
        if self.config.ca_cert:
            cmd.extend(["--cacert", str(cert_dir / "ca.crt")])
        if self.config.client_cert:
            cmd.extend(["--cert", str(cert_dir / "client.cert")])
        if self.config.client_key:
            cmd.extend(["--key", str(cert_dir / "client.key")])
        if self.config.ip:
            cmd.extend(["--resolve", f"{self.config.domain}:443:{self.config.ip}"])
        url = f"https://{self.config.domain}{path}"
        cmd.append(url)

        return self.runner.run(cmd, capture=True, check=check).stdout

    def get_image_tags(self, name: str) -> list[str]:
        try:
            res_str = self.curl(f"/v2/{name}/tags/list")
            res: TagResponse = json.loads(res_str)
            tags = res.get("tags")
            if isinstance(tags, list):
                return [t for t in tags if t]
        except Exception:
            pass
        return []

    def get_manifest_digest(self, name: str, tag: str) -> str:
        headers = self.curl(
            f"/v2/{name}/manifests/{tag}",
            "-I",
            "-H",
            f"Accept: {MANIFEST_ACCEPT}",
        )
        for line in headers.splitlines():
            if line.lower().startswith("docker-content-digest:"):
                return line.split(":", 1)[1].strip()
        raise ValueError(f"Could not resolve Docker-Content-Digest for {name}:{tag}")

    def delete_image_digest(self, name: str, digest: str) -> None:
        self.curl(
            f"/v2/{name}/manifests/{digest}",
            "-X",
            "DELETE",
        )

    def execute(self) -> None:
        keep_tags = self.collect_keep_tags()
        dry_run = os.getenv("REGISTRY_CLEANUP_DRY_RUN", "false").lower() == "true"

        for image in self.images:
            name = image.name
            all_tags = self.get_image_tags(name)
            if not all_tags:
                print(f"No tags found for {name}, skipping cleanup.")
                continue

            # build 'digest' -> 'tag'
            print(f"Checking registry retention for {name}...")
            digest_tags: dict[str, list[str]] = {}
            keep_digests: set[str] = set()
            for tag in all_tags:
                try:
                    digest = self.get_manifest_digest(name, tag)
                except Exception as e:
                    print(f"Failed to get digest for {name}:{tag} - {e}")
                    continue

                digest_tags.setdefault(digest, []).append(tag)
                if tag in keep_tags or not COMMIT_TAG_RE.match(tag):
                    keep_digests.add(digest)

            # delete
            deleted_count = 0
            for digest, tags in digest_tags.items():
                if digest in keep_digests:
                    print(f"Keeping {name} digest {digest} (tags: {', '.join(tags)})")
                    continue

                print(
                    f"Deleting stale {name} digest {digest} (tags: {', '.join(tags)})"
                )
                if dry_run:
                    continue

                try:
                    self.delete_image_digest(name, digest)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete digest {digest} for {name} - {e}")

            print(f"Deleted {deleted_count} stale manifest(s) for {name}")
