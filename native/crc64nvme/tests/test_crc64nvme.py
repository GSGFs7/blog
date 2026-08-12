import os
import random
import subprocess
import sys
import unittest

try:
    import _crc64nvme
except ImportError as error:
    if os.environ.get("CRC64NVME_TEST_CHILD") == "1" and "not supported" in str(error):
        raise SystemExit(77) from error
    raise

MASK = (1 << 64) - 1
POLY = 0x9A6C9329AC4BC9B5


def reference(data, previous=0):
    crc = previous ^ MASK
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (POLY if crc & 1 else 0)
    return crc ^ MASK


class CorrectnessTests(unittest.TestCase):
    def test_selected_backend(self):
        requested = os.environ.get("CRC64NVME_BACKEND")
        if requested and requested != "auto":
            self.assertEqual(_crc64nvme._backend, requested)

    def test_standard_vectors(self):
        cases = (
            (b"", 0),
            (b"123456789", 0xAE8B14860A799888),
            (bytes(4096), 0x6482D367EB22B64E),
            (bytes([255]) * 4096, 0xC0DDBA7302ECA3AC),
        )
        for data, expected in cases:
            with self.subTest(length=len(data), expected=expected):
                self.assertEqual(_crc64nvme.crc64nvme(data), expected)

    def test_every_short_length(self):
        random_source = random.Random(0xC64)
        for length in range(1025):
            data = random_source.randbytes(length)
            previous = random_source.getrandbits(64)
            with self.subTest(length=length):
                self.assertEqual(
                    _crc64nvme.crc64nvme(data, previous),
                    reference(data, previous),
                )

    def test_unaligned_boundaries(self):
        random_source = random.Random(0xA11)
        lengths = (127, 128, 129, 255, 256, 257, 511, 512, 513, 4096)
        offsets = (1, 3, 7, 15, 16, 17, 31, 32, 33, 63)
        for length in lengths:
            raw = random_source.randbytes(length + max(offsets))
            previous = random_source.getrandbits(64)
            for offset in offsets:
                data = memoryview(raw)[offset : offset + length]
                with self.subTest(length=length, offset=offset):
                    self.assertEqual(
                        _crc64nvme.crc64nvme(data, previous),
                        reference(data, previous),
                    )

    def test_incremental_updates(self):
        random_source = random.Random(0x1C4)
        for length in (0, 1, 127, 128, 129, 255, 256, 257, 4096, 65537):
            data = random_source.randbytes(length)
            expected = _crc64nvme.crc64nvme(data)
            splits = {
                0,
                1,
                127,
                128,
                255,
                256,
                length // 2,
                max(0, length - 1),
                length,
            }
            for split in splits:
                if split > length:
                    continue
                with self.subTest(length=length, split=split):
                    previous = _crc64nvme.crc64nvme(data[:split])
                    self.assertEqual(
                        _crc64nvme.crc64nvme(data[split:], previous),
                        expected,
                    )


class BackendMatrixTests(unittest.TestCase):
    @unittest.skipIf(
        os.environ.get("CRC64NVME_TEST_CHILD") == "1",
        "backend matrix child",
    )
    def test_supported_backends(self):
        for backend in ("table", "pclmul", "vpclmul"):
            env = os.environ.copy()
            env["CRC64NVME_BACKEND"] = backend
            env["CRC64NVME_TEST_CHILD"] = "1"
            result = subprocess.run(
                [sys.executable, __file__, "CorrectnessTests"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 77:
                continue
            with self.subTest(backend=backend):
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stdout + result.stderr,
                )

    def test_invalid_backend(self):
        env = os.environ.copy()
        env["CRC64NVME_BACKEND"] = "invalid"
        result = subprocess.run(
            [sys.executable, "-c", "import _crc64nvme"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid CRC64NVME_BACKEND value", result.stderr)


if __name__ == "__main__":
    unittest.main()
