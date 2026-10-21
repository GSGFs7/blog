import mimetypes
import os
import posixpath
from io import TextIOWrapper
from tempfile import SpooledTemporaryFile
from threading import Lock
from typing import IO, AnyStr, Callable, Self
from urllib.parse import quote
from weakref import finalize

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import File
from django.core.files.storage import Storage
from django.core.files.utils import validate_file_name
from django.utils import timezone
from django.utils.deconstruct import deconstructible

from core.r2 import ObjectNotFound, StorageUnavailable, SyncR2Client

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
DERIVED_CACHE_CONTROL = "public, max-age=604800"


class _MediaFile(File):
    def __init__(self, file: IO[AnyStr] | None, name: str | None, mode, storage):
        super().__init__(file, name=name)
        self.mode = mode
        self.storage = storage

    def open(
        self,
        mode: str | None = None,
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        closefd: bool = True,
        opener: Callable[[str, int], int] | None = None,
    ) -> Self:
        if mode is not None and mode != self.mode:
            raise ValueError("Cannot reopen file with a new mode")
        if self.closed:
            self.file = self.storage._download(self.name, self.mode)
            self.__dict__.pop("size", None)
        else:
            self.seek(0)
        return self


@deconstructible
class MediaStorage(Storage):
    def __init__(
        self,
        *,
        bucket_name=None,
        endpoint_url=None,
        access_key=None,
        secret_key=None,
        custom_domain=None,
        querystring_auth=True,
        querystring_expire=3600,
        max_memory_size=None,
        timeout=30.0,
        max_retries=2,
    ):
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.endpoint_url = (endpoint_url or settings.S3_ENDPOINT_URL).rstrip("/")
        self.access_key = access_key or settings.S3_ACCESS_KEY_ID
        self.secret_key = secret_key or settings.S3_SECRET_ACCESS_KEY
        self.custom_domain = custom_domain or settings.S3_PUBLIC_DOMAIN
        self.querystring_auth = querystring_auth
        self.querystring_expire = querystring_expire
        self.max_memory_size = (
            settings.FILE_UPLOAD_MAX_MEMORY_SIZE
            if max_memory_size is None
            else max_memory_size
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        self._client_pid = os.getpid()
        self._client_lock = Lock()
        self._client_finalizer = None

    @property
    def client(self):
        if self._client_pid != os.getpid():
            self._client_lock = Lock()
            self.close()
            self._client_pid = os.getpid()
        with self._client_lock:
            if self._client is None:
                self._client = SyncR2Client(
                    endpoint=self.endpoint_url,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    bucket=self.bucket_name,
                    timeout=self.timeout,
                    max_retries=self.max_retries,
                )
                self._client_finalizer = finalize(self, self._client.close)
            return self._client

    def close(self):
        with self._client_lock:
            if self._client_finalizer is not None:
                self._client_finalizer()
                self._client_finalizer = None
            self._client = None

    @staticmethod
    def _normalize_name(name, *, allow_empty=False):
        name = str(name).replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            raise SuspiciousFileOperation(f"Invalid media path: {name}")
        name = posixpath.normpath(name)
        if allow_empty and name == ".":
            return ""
        validate_file_name(name, allow_relative_path=True)
        return name

    def get_available_name(self, name, max_length=None):
        name = self._normalize_name(name)
        if max_length is None or len(name) <= max_length:
            return name
        directory, filename = posixpath.split(name)
        root, extension = posixpath.splitext(filename)
        root = root[: -(len(name) - max_length)]
        if not root:
            raise SuspiciousFileOperation(f"Media filename exceeds max_length: {name}")
        return posixpath.join(directory, root + extension)

    def get_upload_options(self, name: str):
        options = {
            "content_type": mimetypes.guess_type(name)[0] or "application/octet-stream"
        }

        # add cache control header to R2 metadata
        if name.startswith(("images/raw/", "musics/")):
            # hash indexed image. cache it as long as possible
            options["cache_control"] = IMMUTABLE_CACHE_CONTROL
        elif name.startswith(
            (
                "images/avif/",
                "images/webp/",
                "images/thumbnails/",
                "images/responsive/",
            )
        ):
            options["cache_control"] = DERIVED_CACHE_CONTROL

        return options

    def _save(self, name, content):
        name = self._normalize_name(name)
        if content.seekable():
            content.seek(0)
        options = self.get_upload_options(name)
        options["content_type"] = (
            getattr(content, "content_type", None) or options["content_type"]
        )
        self.client.put(name, content.chunks(), content_length=content.size, **options)
        return name

    def _download(self, name, mode):
        if mode not in {"r", "rb"}:
            raise ValueError("Media files can only be opened in 'r' or 'rb' mode")
        file = SpooledTemporaryFile(
            max_size=self.max_memory_size,
            mode="w+b",
            dir=settings.FILE_UPLOAD_TEMP_DIR,
        )
        try:
            with self.client.get(name) as body:
                for chunk in body.iter_bytes():
                    file.write(chunk)
            file.seek(0)
            return TextIOWrapper(file, encoding="utf-8") if mode == "r" else file
        except BaseException as exc:
            file.close()
            if isinstance(exc, ObjectNotFound):
                raise FileNotFoundError(name) from exc
            raise

    def _open(self, name, mode="rb"):
        name = self._normalize_name(name)
        return _MediaFile(self._download(name, mode), name, mode, self)

    def exists(self, name):
        name = self._normalize_name(name)
        try:
            self.client.stat(name)
        except ObjectNotFound:
            return False
        return True

    def delete(self, name: str):
        name = self._normalize_name(name)
        self.client.delete(name)

    def size(self, name: str):
        name = self._normalize_name(name)
        metadata = self.client.stat(name)
        if metadata.size is None:
            raise StorageUnavailable("R2 object metadata contains no size")
        return metadata.size

    def get_modified_time(self, name: str):
        name = self._normalize_name(name)
        modified = self.client.stat(name).last_modified
        if modified is None:
            raise StorageUnavailable("R2 object metadata contains no modification time")
        return modified if settings.USE_TZ else timezone.make_naive(modified)

    def listdir(self, path: str):
        path = self._normalize_name(path, allow_empty=True)
        prefix = f"{path}/" if path else ""
        directories = set()
        files = set()
        cursor = None
        while True:
            page = self.client.list(prefix=prefix, delimiter="/", cursor=cursor)
            directories.update(
                key.removeprefix(prefix).rstrip("/") for key in page.common_prefixes
            )
            files.update(
                obj.key.removeprefix(prefix)
                for obj in page.objects
                if obj.key != prefix and not obj.key.endswith("/")
            )
            if not page.is_truncated:
                break
            if page.next_cursor is None or page.next_cursor == cursor:
                raise StorageUnavailable("R2 object listing returned an invalid cursor")
            cursor = page.next_cursor
        return sorted(directories), sorted(files)

    def url(self, name: str | None):
        name = self._normalize_name(name)
        if self.custom_domain:
            return f"https://{self.custom_domain.rstrip('/')}/{quote(name, safe='/~')}"
        if self.querystring_auth:
            return self.client.presign("GET", name, expires_in=self.querystring_expire)
        return (
            f"{self.endpoint_url}/{quote(self.bucket_name, safe='')}/"
            f"{quote(name, safe='/~')}"
        )
