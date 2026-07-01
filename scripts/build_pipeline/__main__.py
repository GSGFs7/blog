#!/usr/bin/env python3

"""
refactor from `script/build-and-push.sh`
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Sequence

from .config import IMAGES
from .pipeline import Pipeline
from .runner import SubprocessRunner
from .task import BuildImageTask, CleanImageTask, PushImageTask, SetRegistryCertTask
from .type import Task

ROOT = Path(__file__).resolve().parent.parent.parent
COMMIT_TAG_RE = re.compile(r"^[0-9a-f]{40}$")


def init():
    commit_hash = os.getenv("CI_COMMIT_SHA", "")
    if not COMMIT_TAG_RE.match(commit_hash):
        # TODO: message
        print()


def main() -> int:
    try:
        init()

        runner = SubprocessRunner(ROOT)
        tasks: Sequence[Task] = (
            SetRegistryCertTask(),
            BuildImageTask(runner, IMAGES),
            PushImageTask(runner, IMAGES),
            CleanImageTask(runner, IMAGES),
        )

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
