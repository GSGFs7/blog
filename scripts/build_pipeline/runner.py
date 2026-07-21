import subprocess
import sys
from pathlib import Path

from .type import Runner


class SubprocessRunner(Runner):
    def __init__(self, cwd: str | Path):
        self.cwd = cwd

    @staticmethod
    def log_command(args: list[str]):
        cmd_str = " ".join(args)
        if sys.stdout.isatty():
            print(f"\033[36m$ {cmd_str}\033[0m", flush=True)
        else:
            print(f"$ {cmd_str}", flush=True)

    def run(
        self,
        args: list[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            self.log_command(args)
            return subprocess.run(
                args,
                cwd=self.cwd,
                check=check,
                text=True,
                capture_output=capture,
            )
        except subprocess.CalledProcessError as e:
            if e.stdout:
                print("--- Subprocess stdout ---", flush=True)
                print(e.stdout, end="", flush=True)
            if e.stderr:
                print("--- Subprocess stderr ---", file=sys.stderr, flush=True)
                print(e.stderr, file=sys.stderr, end="", flush=True)

            error_msg = (
                f"Error: Command '{' '.join(args)}' failed "
                f"with exit status {e.returncode}."
            )
            if sys.stderr.isatty():
                print(f"\033[1;31m{error_msg}\033[0m", file=sys.stderr, flush=True)
            else:
                print(error_msg, file=sys.stderr, flush=True)
            raise e
