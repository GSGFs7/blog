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
