import asyncio
import os
import shutil
import struct
import unittest
import zlib
from io import BytesIO
from unittest.mock import Mock, patch

from media_service.exiftool import AsyncExifTool, SyncExifTool


def make_png():
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"tEXt", b"Comment\x00metadata-to-remove")
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


class ExifToolArgumentSecurityTest(unittest.TestCase):
    def setUp(self):
        self.tool = object.__new__(SyncExifTool)
        self.tool.process = Mock()
        self.tool._counter = 0

    def test_execute_rejects_control_characters_before_process_access(self):
        for char in ("\r", "\n", "\x00"):
            with self.subTest(char=repr(char)):
                with self.assertRaises(ValueError):
                    self.tool.execute("-all=", f"input.png{char}-ver")
        self.assertEqual(self.tool._counter, 0)
        self.assertEqual(self.tool.process.mock_calls, [])

    def test_clean_rejects_control_characters_anywhere_in_filename(self):
        for filename in (
            "probe.png\n-echo1\nEXIFTOOL_ARGUMENT_INJECTED",
            "probe.png\r-ver",
            "probe.png\x00",
            "probe\n.png",
        ):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    self.tool.clean(BytesIO(make_png()), filename)
        self.assertEqual(self.tool.process.mock_calls, [])

    def test_async_clean_rejects_injection(self):
        with patch.object(SyncExifTool, "_instance", self.tool):
            with self.assertRaises(ValueError):
                asyncio.run(
                    AsyncExifTool().clean(BytesIO(make_png()), "probe.png\n-ver")
                )
        self.assertEqual(self.tool.process.mock_calls, [])


@unittest.skipUnless(shutil.which("exiftool"), "exiftool is not available")
class ExifToolSafeFilenameTest(unittest.TestCase):
    def setUp(self):
        self.tool = object.__new__(SyncExifTool)
        self.tool.process = None
        self.tool._counter = 0

    def tearDown(self):
        self.tool.terminate()

    def test_cleans_metadata_with_safe_temporary_names(self):
        for filename, suffix in (
            ("photo.png", ".png"),
            ("照片.PNG", ".png"),
            ("photo", ""),
            (None, ""),
            ("photo.untrusted", ""),
            ("photo.png -ver", ""),
        ):
            with self.subTest(filename=filename):
                with patch.object(
                    self.tool, "_execute", wraps=self.tool._execute
                ) as execute:
                    result = self.tool.clean(BytesIO(make_png()), filename)
                self.assertTrue(result.getvalue().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertNotIn(b"metadata-to-remove", result.getvalue())
                args = execute.call_args.args
                self.assertEqual(os.path.basename(args[1]), f"input{suffix}")
                self.assertEqual(os.path.basename(args[3]), f"output{suffix}")

    def test_rejected_injection_does_not_break_next_request(self):
        self.tool.clean(BytesIO(make_png()), "before.png")
        process = self.tool.process
        with self.assertRaises(ValueError):
            self.tool.execute("input.png\n-echo1\nEXIFTOOL_ARGUMENT_INJECTED")
        result = self.tool.clean(BytesIO(make_png()), "after.png")
        self.assertIs(self.tool.process, process)
        self.assertNotIn(b"metadata-to-remove", result.getvalue())
