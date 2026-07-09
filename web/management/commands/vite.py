import shutil
import subprocess
import sys

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand, CommandError, handle_default_options
from django.core.management.base import SystemCheckError
from django.db import connections


def _try_npm_tools() -> list[str]:
    if shutil.which("pnpm"):
        return ["pnpm", "exec", "vite"]
    if shutil.which("npm"):
        return ["npm", "exec", "vite"]

    raise RuntimeError("no available npm command")


class Command(BaseCommand):
    help = "Run Vite from Django."

    def run_from_argv(self, argv):
        parser = self.create_parser(argv[0], argv[1])
        options, unknown_args = parser.parse_known_args(argv[2:])
        cmd_options = vars(options)
        cmd_options["vite_args"] = unknown_args
        handle_default_options(options)

        try:
            self.execute(**cmd_options)
        except CommandError as e:
            if options.traceback:
                raise

            if isinstance(e, SystemCheckError):
                self.stderr.write(str(e), lambda x: x)
            else:
                self.stderr.write(f"{e.__class__.__name__}: {e}")
            sys.exit(e.returncode)
        except KeyboardInterrupt:
            sys.exit(0)
        finally:
            try:
                connections.close_all()
            except ImproperlyConfigured:
                pass

    def handle(self, *args, **options):
        vite_args = options.get("vite_args") or ["dev"]
        try:
            command = [*_try_npm_tools(), *vite_args]
        except RuntimeError as exc:
            raise CommandError(str(exc))

        if options.get("verbosity", 1) >= 1:
            self.stdout.write(
                self.style.NOTICE(f"Starting Vite with: {' '.join(command)}")
            )

        try:
            subprocess.run(command, cwd=settings.BASE_DIR, check=True)
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\nStopped Vite dev server."))
        except FileNotFoundError as exc:
            raise CommandError(f"Failed to start Vite: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"Vite exited with status {exc.returncode}.") from exc
