import os

from ..type import Runner, Task

ENV_NAMES = (
    "CI_COMMIT_SHA",
    "STATIC_ASSET_ENDPOINT_URL",
    "STATIC_ASSET_BUCKET",
    "STATIC_ASSET_ACCESS_KEY_ID",
    "STATIC_ASSET_SECRET_ACCESS_KEY",
    "STATIC_ASSET_PREFIX",
    "STATIC_ASSET_PUBLIC_URL",
    "STATIC_ASSET_ALLOWED_ORIGIN",
)


class PublishStaticAssetsTask(Task):
    def __init__(self, runner: Runner):
        self.runner = runner

    def execute(self) -> None:
        missing = [name for name in ENV_NAMES if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                f"Static asset configuration is missing: {', '.join(missing)}"
            )

        command = ["podman", "run", "--rm"]
        for name in ENV_NAMES:
            command.extend(["--env", name])
        command.extend(
            [
                "localhost/blog-app:latest",
                "python",
                "-m",
                "scripts.publish_static_assets",
            ]
        )
        self.runner.run(command)
