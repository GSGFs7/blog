from .image_base import BaseImageTask, Config


class BuildImageTask(BaseImageTask):
    def build(self, config: Config):
        # fmt: off
        cmd = [
            "podman", "build",
            # file
            "-f", config.dockerfile,
            # name
            "-t", f"localhost/{config.name}:latest",
        ]
        # fmt: on
        if config.target is not None:
            cmd.extend(["--target", config.target])
        self.runner.run(cmd)

    def execute(self) -> None:
        for image in self.images:
            self.build(image)
