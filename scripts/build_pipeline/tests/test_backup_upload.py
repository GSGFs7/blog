import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.upload import main, upload_file


class BackupUploadTest(unittest.TestCase):
    def setUp(self):
        dotenv = patch("scripts.upload.dotenv.load_dotenv")
        dotenv.start()
        self.addCleanup(dotenv.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "backup.sql.gz"
        self.path.write_bytes(b"backup")

    def test_uploads_to_backup_prefix_and_closes_client(self):
        boto3 = Mock()
        environment = {
            "S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
            "S3_ACCESS_KEY_ID": "access-key",
            "S3_SECRET_ACCESS_KEY": "secret-key",
        }
        client = Mock()
        boto3.client.return_value.__enter__ = Mock(return_value=client)
        boto3.client.return_value.__exit__ = Mock(return_value=False)
        with (
            patch.dict(sys.modules, {"boto3": boto3}),
            patch.dict("os.environ", environment, clear=True),
        ):
            upload_file(self.path, "backups", "backups/")

        boto3.client.assert_called_once_with(
            "s3",
            endpoint_url=environment["S3_ENDPOINT_URL"],
            aws_access_key_id="access-key",
            aws_secret_access_key="secret-key",
            region_name="auto",
        )
        client.upload_file.assert_called_once_with(
            str(self.path), "backups", "backups/backup.sql.gz"
        )
        boto3.client.return_value.__exit__.assert_called_once()

    @patch("scripts.upload.upload_file")
    def test_exit_status_reports_upload_failure(self, upload):
        arguments = ["upload.py", "upload", str(self.path), "backups", "backups/"]
        with patch.object(sys, "argv", arguments):
            self.assertEqual(main(), 0)
            upload.assert_called_once_with(self.path, "backups", "backups/")
            upload.side_effect = RuntimeError("connection failed")
            self.assertEqual(main(), 1)

    @patch("scripts.upload.upload_file")
    def test_missing_backup_fails_without_uploading(self, upload):
        self.path.unlink()
        with patch.object(
            sys, "argv", ["upload.py", "upload", str(self.path), "backups"]
        ):
            self.assertEqual(main(), 1)
        upload.assert_not_called()
