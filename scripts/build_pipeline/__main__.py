#!/usr/bin/env python3

"""
refactor from `script/build-and-push.sh`
"""

import os
import re
import subprocess
from pathlib import Path

from .config import IMAGES
from .pipeline import Pipeline
from .runner import SubprocessRunner
from .task import (
    BuildImageTask,
    CheckRegistryRouteTask,
    CleanImageTask,
    PushImageTask,
    RegistryConfig,
    SetRegistryCertTask,
)
from .type import Task

ROOT = Path(__file__).resolve().parent.parent.parent
COMMIT_TAG_RE = re.compile(r"^[0-9a-f]{40}$")


def init():
    commit_hash = os.getenv("CI_COMMIT_SHA", "")
    if COMMIT_TAG_RE.fullmatch(commit_hash) is None:
        raise ValueError(
            "CI_COMMIT_SHA must be a 40-character lowercase hexadecimal commit SHA"
        )


def env_bool(name: str, default: bool):
    value = os.getenv(name, None)
    if value is None:
        return default
    return value.lower() in ("1", "yes", "true")


def main() -> int:
    try:
        init()

        runner = SubprocessRunner(ROOT)
        registry_config = RegistryConfig.for_env()
        tasks: list[Task] = [
            SetRegistryCertTask(registry_config),
            CheckRegistryRouteTask(runner, registry_config),
            BuildImageTask(runner, IMAGES),
            PushImageTask(runner, IMAGES, registry_config),
        ]
        if env_bool("REGISTRY_CLEANUP_ENABLED", True):
            try:
                tasks.append(CleanImageTask(runner, IMAGES, registry_config))
            except Exception as e:
                if env_bool("REGISTRY_CLEANUP_REQUIRED", True):
                    raise e
                print("Warning: registry cleanup failed", e)

        os.chdir(ROOT)
        pipeline = Pipeline(tasks)
        pipeline.execute()
    except subprocess.CalledProcessError:
        return 1
    except Exception as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
