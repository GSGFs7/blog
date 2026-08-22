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


class AsyncExifTool:
    # class attribute
    _instance = None
    _lock = asyncio.Lock()
    _is_available = None

    # instance attribute
    process: asyncio.subprocess.Process | None
    _counter: int
    _loop: asyncio.AbstractEventLoop | None

    def __new__(cls, *args, **kwargs):
        # in classic ASGI python env
        # this sync function will run in main thread (native atomicity)
        if cls._instance is None:
            cls._instance = super(AsyncExifTool, cls).__new__(cls)
            cls._instance.process = None
            cls._instance._counter = 0
            # prevent calling across event loops
            # in product, there is only one event loop normally
            cls._instance._loop = None
        return cls._instance

    async def _start_process(self):
        current_loop = asyncio.get_running_loop()
        if self.process is not None and self.process.returncode is None:
            if self._loop is current_loop:
                return
            # expose problems in advance
            raise RuntimeError("AsyncExifTool is still running on another event loop")

        try:
            args = ["exiftool", "-stay_open", "True", "-@", "-"]
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._loop = current_loop
        except FileNotFoundError:
            logger.info("ExifTool not found. Some features will be disabled.")
            self.process = None

    async def _ensure_process(self):
        current_loop = asyncio.get_running_loop()
        if (
            self.process is None
            or self.process.returncode is not None
            or self._loop != current_loop
        ):
            await self._start_process()
        if self.process is None:
            raise RuntimeError("ExifTool process failed to start.")

    async def _execute(self, *args: str) -> str:
        """core execute logic, without lock"""

        await self._ensure_process()

        try:
            self._counter += 1
            exec_id = self._counter
            sentinel = f"{{ready{exec_id}}}".encode()

            cmd = "\n".join(args) + "\n" + f"-execute{exec_id}\n"
            self.process.stdin.write(cmd.encode())
            await self.process.stdin.drain()

            response = bytearray()
            while True:
                chunk = await self.process.stdout.read(4096)
                if not chunk:
                    break
                response.extend(chunk)
                if sentinel in response:
                    break

            return (
                response.decode("utf-8", errors="ignore")
                .replace(f"{{ready{exec_id}}}", "")
                .strip()
            )
        except Exception as e:
            await self.terminate()
            raise e

    async def execute(self, *args: str) -> str:
        """Execute any ExifTool command."""

        async with self._lock:
            return await self._execute(*args)

    async def clean(self, data: IO[bytes], filename: str | None = None) -> BytesIO:
        """clean image EXIF data"""

        async with self._lock:
            tmp_base = (
                "/dev/shm"
                if os.path.exists("/dev/shm") and os.access("/dev/shm", os.W_OK)
                else None
            )

            tmp_dir = await asyncio.to_thread(
                tempfile.mkdtemp, dir=tmp_base, prefix="blog-async-exif-"
            )

            try:
                ext = os.path.splitext(filename)[-1] if filename else ""
                tmp_in = os.path.join(tmp_dir, f"input{ext}")
                tmp_out = os.path.join(tmp_dir, f"output{ext}")

                def _prepare():
                    if hasattr(data, "seekable") and data.seekable():
                        data.seek(0)
                    with open(tmp_in, "wb") as f:
                        # noinspection PyTypeChecker
                        shutil.copyfileobj(data, f)

                await asyncio.to_thread(_prepare)

                # execute without lock
                response = await self._execute("-all=", tmp_in, "-o", tmp_out)

                def _read():
                    if not os.path.exists(tmp_out):
                        raise RuntimeError(f"ExifTool failed: {response}")
                    with open(tmp_out, "rb") as f:
                        return BytesIO(f.read())

                return await asyncio.to_thread(_read)
            except Exception as e:
                # reset
                await self.terminate()
                raise e
            finally:
                await asyncio.to_thread(
                    lambda: shutil.rmtree(tmp_dir, ignore_errors=True)
                )

    async def terminate(self):
        process: asyncio.subprocess.Process | None = self.process
        owner_loop: asyncio.AbstractEventLoop = self._loop

        self.process = None
        self._loop = None
        if process is None:
            return

        current_loop = asyncio.get_running_loop()
        if owner_loop is not current_loop:
            raise RuntimeError(
                "AsyncExifTool must be terminated on the event loop that created it"
            )

        try:
            if process.stdin is not None:
                process.stdin.write(b"-stay_open\nFalse\n")
                await process.stdin.drain()
                process.stdin.close()

            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()

    @classmethod
    async def is_available(cls) -> bool:
        # lru_cache not support async
        # use a class var store the result
        if cls._is_available is not None:
            return cls._is_available

        try:
            args = ["exiftool", "-ver"]
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            cls._is_available = process.returncode == 0
        except Exception:
            cls._is_available = False

        return cls._is_available
