from collections.abc import Buffer

_backend: str

def crc64nvme(data: Buffer, previous: int = 0) -> int: ...
