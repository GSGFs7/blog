import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from functools import lru_cache
from io import BytesIO
from typing import IO

logger = logging.getLogger(__name__)


class SyncExifTool:
    # class attribute
    _instance = None  # single instance
    _lock = threading.Lock()  # thread safety

    # instance attribute
    process: subprocess.Popen | None
    _counter: int

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncExifTool, cls).__new__(cls, *args, **kwargs)
                cls._instance._start_process()
        return cls._instance

    def _start_process(self):
        """Replace __init__"""

        # ExifTool (https://exiftool.org/)
        # persistence ExifTool process
        # args:
        #  -stay_open True: keep process running
        #  -@ -: read parameters from stdin
        # Capture stderr to stdout for easier error diagnostic
        try:
            self.process = subprocess.Popen(
                ["exiftool", "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
        except FileNotFoundError:
            logger.info("ExifTool not found. Some features will be disabled.")
            self.process = None

        self._counter = 0

    def _ensure_process_running(self):
        if self.process is None or self.process.poll() is not None:
            self._start_process()

        if self.process is None:
            raise RuntimeError("ExifTool process is not running.")

    def _execute(self, *args: str):
        """execute a command without lock"""

        self._ensure_process_running()

        try:
            self._counter += 1
            exec_id = self._counter
            sentinel = f"{{ready{exec_id}}}".encode("utf-8")

            # Prepare arguments, each on a new line as per -@ - format
            cmd_args = "\n".join(args) + f"\n-execute{exec_id}\n"
            self.process.stdin.write(cmd_args.encode("utf-8"))
            self.process.stdin.flush()

            # Read from stdout until we see the sentinel
            response = bytearray()
            while True:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                response.extend(chunk)
                if sentinel in response:
                    break

            # Decode and strip the sentinel
            return (
                response.decode("utf-8", errors="ignore")
                .replace(f"{{ready{exec_id}}}", "")
                .strip()
            )
        except Exception as e:
            self.terminate()  # Reset process on error
            raise e

    def execute(self, *args: str) -> str:
        """
        Execute a custom ExifTool command.
        """

        with self._lock:
            return self._execute(*args)

    def clean(self, data: IO[bytes], filename: str | None = None) -> BytesIO:
        """clean image EXIF data"""

        with self._lock:
            self._ensure_process_running()

            # prefer /dev/shm, makesure we are using tmpfs
            tmp_base = (
                "/dev/shm"
                if os.path.exists("/dev/shm") and os.access("/dev/shm", os.W_OK)
                else None
            )

            with tempfile.TemporaryDirectory(
                dir=tmp_base, prefix="blog-exiftool-", delete=True
            ) as tmp_dir:
                ext = os.path.splitext(filename)[-1] if filename else ""
                tmp_in = os.path.join(tmp_dir, f"input{ext}")
                tmp_out = os.path.join(tmp_dir, f"output{ext}")

                if hasattr(data, "seekable") and data.seekable():
                    data.seek(0)

                with open(tmp_in, "wb") as f:
                    # noinspection PyTypeChecker
                    shutil.copyfileobj(data, f)

                # execute clean
                response = self._execute("-all=", tmp_in, "-o", tmp_out)

                if not os.path.exists(tmp_out):
                    raise RuntimeError(
                        f"ExifTool failed: {response or 'No output file created'}"
                    )

                with open(tmp_out, "rb") as f:
                    return BytesIO(f.read())

    def terminate(self):
        process = self.process

        self.process = None
        if process is None:
            return

        try:
            if process.stdin is not None:
                try:
                    process.stdin.write(b"-stay_open\nFalse\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    process.stdin.close()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()

    @staticmethod
    @lru_cache(1)
    def is_available() -> bool:
        try:
            subprocess.run(
                ["exiftool", "-ver"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except Exception:
            return False


# async subprocess will case some threading issue, sync is enough.
# it only reproduced in the test env, prod unaffected. (typical asgi only one loop)
class AsyncExifTool:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AsyncExifTool, cls).__new__(cls)
        return cls._instance

    @property
    def process(self) -> subprocess.Popen | None:
        instance = SyncExifTool._instance
        return instance.process if instance is not None else None

    async def execute(self, *args: str) -> str:
        """Execute any ExifTool command."""

        return await asyncio.to_thread(SyncExifTool().execute, *args)

    async def clean(self, data: IO[bytes], filename: str | None = None) -> BytesIO:
        """clean image EXIF data"""

        return await asyncio.to_thread(SyncExifTool().clean, data, filename)

    async def terminate(self):
        instance = SyncExifTool._instance
        if instance is not None:
            await asyncio.to_thread(instance.terminate)

    @classmethod
    async def is_available(cls) -> bool:
        return await asyncio.to_thread(SyncExifTool.is_available)
