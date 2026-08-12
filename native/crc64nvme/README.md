# crc64nvme-native

Native CRC-64/NVME implementation.

```python
from _crc64nvme import crc64nvme

checksum = crc64nvme(b"123456789")
checksum = crc64nvme(next_chunk, checksum)
```

`data` must expose a contiguous, readable buffer. `previous` must be an integer
between `0` and `2**64 - 1`.

Generate the local clangd configuration with:

```bash
uv run python native/crc64nvme/scripts/configure_clangd.py
```

Run the performance benchmark with:

```bash
uv run python native/crc64nvme/scripts/benchmark.py
```

The implementation selects the fastest supported backend at import time. Set
`CRC64NVME_BACKEND` to `table`, `pclmul`, or `vpclmul` to force a backend for
testing. Importing the module fails if the requested backend is unavailable.

Run the correctness tests, including every supported backend, with:

```bash
uv sync --reinstall-package crc64nvme-native
uv run python -m unittest native/crc64nvme/tests/test_crc64nvme.py
```
