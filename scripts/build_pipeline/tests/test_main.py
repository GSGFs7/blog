import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.build_pipeline.__main__ import init, main


class CommitShaValidationTest(unittest.TestCase):
    def test_main_fails_for_invalid_commit_sha(self):
        invalid_values = (
            None,
            "",
            "a" * 39,
            "g" * 40,
            "A" * 40,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                env = {} if value is None else {"CI_COMMIT_SHA": value}
                with (
                    patch.dict(os.environ, env, clear=True),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(), 1)

    def test_init_accepts_valid_commit_sha(self):
        with patch.dict(os.environ, {"CI_COMMIT_SHA": "a" * 40}, clear=True):
            init()


if __name__ == "__main__":
    unittest.main()
