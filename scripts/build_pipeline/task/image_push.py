import os

from .cert import Config
from .image_base import BaseImageTask


class PushImageTask(BaseImageTask):
    def __init__(self, runner, images, config: Config | None = None):
        super().__init__(runner, images)
        if config is None:
            self.config = Config.for_env()
        else:
            self.config = config

    def tag(self, name: str, tag: str):
        self.runner.run(["podman", "tag", f"localhost/{name}:latest", tag])

    def push(self, tag: str):
        self.runner.run(["podman", "push", tag])

    def execute(self) -> None:
        for image in self.images:
            commit_hash = os.getenv("CI_COMMIT_SHA", "latest")
            hash_tag = f"{self.config.domain}/{image.name}:{commit_hash}"
            latest_tag = f"{self.config.domain}/{image.name}:latest"
            self.tag(image.name, hash_tag)
            self.tag(image.name, latest_tag)
            self.push(hash_tag)
            self.push(latest_tag)
