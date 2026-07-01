from typing import Sequence

from .type import Task


class Pipeline:
    def __init__(self, tasks: Sequence[Task]):
        self.tasks = tasks

    def execute(self) -> None:
        for task in self.tasks:
            # TODO: logging now task
            print()
            task.execute()
