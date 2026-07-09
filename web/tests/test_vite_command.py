from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.core.management.base import OutputWrapper
from django.test import SimpleTestCase, override_settings

from web.management.commands.vite import Command


@override_settings(BASE_DIR="/tmp/blog")
class ViteCommandTests(SimpleTestCase):
    @patch("web.management.commands.vite.shutil.which")
    @patch("web.management.commands.vite.subprocess.run")
    def test_defaults_to_vite_dev_via_pnpm(self, run, which):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name == "pnpm" else None

        call_command("vite", stdout=StringIO())

        run.assert_called_once_with(
            ["pnpm", "exec", "vite", "dev"], cwd="/tmp/blog", check=True
        )

    @patch("web.management.commands.vite.shutil.which")
    @patch("web.management.commands.vite.subprocess.run")
    def test_passes_arguments_through_to_vite(self, run, which):
        which.side_effect = lambda name: f"/usr/bin/{name}" if name == "pnpm" else None

        cmd = Command()
        cmd.stdout = OutputWrapper(StringIO())
        cmd.run_from_argv(["manage.py", "vite", "build", "--watch"])

        run.assert_called_once_with(
            ["pnpm", "exec", "vite", "build", "--watch"],
            cwd="/tmp/blog",
            check=True,
        )

    @patch("web.management.commands.vite.shutil.which", return_value=None)
    def test_raises_when_no_package_manager_is_available(self, _which):
        with self.assertRaisesMessage(CommandError, "no available npm command"):
            call_command("vite", stdout=StringIO())
