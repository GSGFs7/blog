import os

from .image_base import BaseImageTask, Config


class BuildImageTask(BaseImageTask):
    def build(self, config: Config):
        cmd = [
            "podman",
            "build",
            "-f",
            config.dockerfile,
        ]
        # build arg
        if config.name == "blog-app":
            cmd.extend(["--build-arg", f"BUILD_ID={os.environ['CI_COMMIT_SHA']}"])
        # image tag
        cmd.extend(["-t", f"localhost/{config.name}:latest"])
        # build target
        if config.target is not None:
            cmd.extend(["--target", config.target])
        # context
        cmd.append(".")

        self.runner.run(cmd)

    def execute(self) -> None:
        for image_config in self.images:
            self.build(image_config)
