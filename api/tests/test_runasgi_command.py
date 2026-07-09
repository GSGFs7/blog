from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from api.management.commands.runasgi import parse_addr


@override_settings(BASE_DIR="/tmp/blog")
class RunAsgiCommandTests(SimpleTestCase):
    @patch("api.management.commands.runasgi.Command.check_migrations")
    @patch("api.management.commands.runasgi.run")
    def test_runs_uvicorn_with_development_defaults(self, run, _check_migrations):
        call_command("runasgi", stdout=StringIO())

        run.assert_called_once_with(
            "blog.asgi:application",
            host="127.0.0.1",
            port=8000,
            reload=True,
            reload_dirs=["/tmp/blog"],
            workers=1,
            log_level="info",
            access_log=True,
        )

    @patch("api.management.commands.runasgi.Command.check_migrations")
    @patch("api.management.commands.runasgi.run")
    def test_accepts_production_style_options(self, run, _check_migrations):
        call_command(
            "runasgi",
            "0.0.0.0:9000",
            reload=False,
            workers=3,
            log_level="warning",
            access_log=False,
            stdout=StringIO(),
        )

        run.assert_called_once_with(
            "blog.asgi:application",
            host="0.0.0.0",
            port=9000,
            reload=False,
            reload_dirs=None,
            workers=3,
            log_level="warning",
            access_log=False,
        )

    def test_parses_port_and_ipv6(self):
        self.assertEqual(parse_addr("9000"), ("127.0.0.1", 9000))
        self.assertEqual(parse_addr("[::1]:9000"), ("::1", 9000))

    @patch("api.management.commands.runasgi.Command.check_migrations")
    def test_rejects_invalid_options(self, _check_migrations):
        with self.assertRaisesMessage(CommandError, "Invalid port: 0"):
            parse_addr("0")
        with self.assertRaisesMessage(
            CommandError, "--workers greater than 1 requires --no-reload"
        ):
            call_command("runasgi", workers=2, stdout=StringIO())
