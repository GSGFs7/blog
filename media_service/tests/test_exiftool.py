import asyncio
import tempfile
import unittest
from io import BytesIO

import requests
from django.test import TestCase
from PIL import Image as PILImage

from media_service.exiftool import AsyncExifTool, SyncExifTool

# About:
#   Everson Museum of Art, Syracuse, New York, 1969. Photo by Carol M. Highsmith.
#   From the Carol M. Highsmith Archive, Library of Congress.
# License: CC-BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)
# Source: https://commons.wikimedia.org/wiki/File:Everson_Museum_of_Art,_Syracuse,_New_York,_1969,_currently_digitized.jpg
test_image_url = "https://img.gsgfs.moe/img/e4846b98c3a31f6139ac51922477fd52.jpg"


class ExifToolTest(TestCase):
    test_image_data = None

    @classmethod
    def setUpClass(cls):
        if not SyncExifTool.is_available():
            raise unittest.SkipTest("exiftool is not available")

        url = test_image_url
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            cls.test_image_data = resp.content
        except Exception as e:
            raise unittest.SkipTest(f"Failed to fetch image: {e}")

        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        try:
            instance = SyncExifTool._instance
            if instance is not None:
                instance.terminate()
        finally:
            SyncExifTool._instance = None
            super().tearDownClass()

    def test_single_instance(self):
        et1 = SyncExifTool()
        et2 = SyncExifTool()
        self.assertIs(et1, et2)

    def test_is_available(self):
        """If initialization is complete is_available must return True"""
        self.assertTrue(SyncExifTool.is_available())

    def test_clean_metadata(self):
        if not self.test_image_data:
            self.skipTest("No test image data available")

        et = SyncExifTool()
        original_data = self.test_image_data

        # clean metadata
        cleaned_io = et.clean(BytesIO(original_data), "test.jpg")
        cleaned_data = cleaned_io.getvalue()

        # The data should be different
        self.assertNotEqual(original_data, cleaned_data)

        # verify the metadata is gone
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            tmp.write(cleaned_data)
            tmp_name = tmp.name

            result = SyncExifTool().execute(
                "-Software", "-CreatorTool", "-HistoryAction", tmp_name
            )
            # metadata should be removed
            self.assertEqual(result.strip(), "")

    def test_clean_invalid_data(self):
        et = SyncExifTool()
        invalid_data = b"not an image file content"

        with self.assertRaises(RuntimeError):
            et.clean(BytesIO(invalid_data), filename="test.jpg")

    def test_persistence(self):
        et = SyncExifTool()
        buffer = BytesIO()
        PILImage.new("RGB", (1, 1)).save(buffer, "PNG")

        buffer.seek(0)
        et.clean(buffer, filename="test.png")
        process_id = et.process.pid
        self.assertIsNotNone(et.process)

        buffer.seek(0)
        et.clean(buffer, filename="test.png")
        self.assertEqual(et.process.pid, process_id)

    def test_terminate_closes_process_pipes(self):
        et = SyncExifTool()
        process = et.process

        et.terminate()

        self.assertIsNone(et.process)
        self.assertIsNotNone(process.returncode)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)


class AsyncExifToolTest(unittest.IsolatedAsyncioTestCase):
    test_image_data = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not SyncExifTool.is_available():
            raise unittest.SkipTest("exiftool is not available")

        url = test_image_url
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            cls.test_image_data = resp.content
        except Exception as e:
            raise unittest.SkipTest(f"Failed to fetch image: {e}")

    async def asyncTearDown(self):
        instance = AsyncExifTool._instance
        if instance is not None:
            await instance.terminate()

        AsyncExifTool._instance = None

    async def test_async_single_instance(self):
        et1 = AsyncExifTool()
        et2 = AsyncExifTool()
        self.assertIs(et1, et2)

    async def test_async_is_available(self):
        self.assertTrue(await AsyncExifTool.is_available())

    async def test_async_clean_metadata(self):
        if not self.test_image_data:
            self.skipTest("No test image data available")

        et = AsyncExifTool()
        original_data = self.test_image_data

        # clean metadata
        cleaned_io = await et.clean(BytesIO(original_data), "test.jpg")
        cleaned_data = cleaned_io.getvalue()

        # The data should be different
        self.assertNotEqual(original_data, cleaned_data)

        # verify the metadata is gone
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            tmp.write(cleaned_data)
            tmp_name = tmp.name

            result = await AsyncExifTool().execute(
                "-Software", "-CreatorTool", "-HistoryAction", tmp_name
            )
            # metadata should be removed
            self.assertEqual(result.strip(), "")

    async def test_async_persistence(self):
        et = AsyncExifTool()
        buffer = BytesIO()
        # PIL save is blocking
        await asyncio.to_thread(PILImage.new("RGB", (1, 1)).save, buffer, "PNG")

        buffer.seek(0)
        await et.clean(buffer, filename="test.png")
        self.assertIsNotNone(et.process)
        process_id = et.process.pid

        buffer.seek(0)
        await et.clean(buffer, filename="test.png")
        self.assertEqual(et.process.pid, process_id)
