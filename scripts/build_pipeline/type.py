import subprocess
from typing import Protocol


class Task(Protocol):
    def execute(self) -> None: ...


class Runner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]: ...
