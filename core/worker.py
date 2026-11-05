import os

from uvicorn.workers import UvicornWorker


class BoundedUvicornWorker(UvicornWorker):
    def __init__(self, *args, **kwargs):
        value = os.environ.get("UVICORN_LIMIT_CONCURRENCY", "20")

        try:
            limit = int(value)
        except ValueError:
            raise ValueError(
                "UVICORN_LIMIT_CONCURRENCY must be a positive integer"
            ) from None

        if limit < 1:
            raise ValueError("UVICORN_LIMIT_CONCURRENCY must be a positive integer")

        self.CONFIG_KWARGS = {
            **self.CONFIG_KWARGS,
            "limit_concurrency": limit,
        }
        super().__init__(*args, **kwargs)
