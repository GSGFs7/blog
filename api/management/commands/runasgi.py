from django.conf import settings
from django.core.management import BaseCommand, CommandError
from uvicorn import run


class Command(BaseCommand):
    help = "Run Django ASGI application with Uvicorn."
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
            "addr",
            nargs="?",
            default="127.0.0.1:8000",
            help="Optional address and port, for example 0.0.0.0:8000 or 8000.",
        )
        parser.add_argument(
            "--no-reload",
            action="store_false",
            default=True,
            dest="reload",
            help="Disable automatic code reloading.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Number of worker processes. "
            "Requires --no-reload when greater than 1.",
        )
        parser.add_argument(
            "--log-level",
            choices=("critical", "error", "warning", "info", "debug", "trace"),
            default="info",
        )
        parser.add_argument(
            "--no-access-log",
            action="store_false",
            default=True,
            dest="access_log",
            help="Disable the Uvicorn access log.",
        )

    def handle(self, *args, **options):
        host, port = parse_addr(options["addr"])
        reload = options["reload"]
        workers = options["workers"]

        if workers < 1:
            raise CommandError("Workers must be at least 1")
        if reload and workers > 1:
            raise CommandError("--workers greater than 1 requires --no-reload")

        # settings.ASGI_APPLICATION -> "blog.asgi.application"
        # uvicorn's format: "blog.asgi:application"
        asgi_app = settings.ASGI_APPLICATION
        if ":" not in asgi_app:
            module, attr = asgi_app.rsplit(".", 1)
            asgi_app = f"{module}:{attr}"

        run(
            asgi_app,
            host=host,
            port=port,
            reload=reload,
            reload_dirs=[str(settings.BASE_DIR)] if reload else None,
            workers=workers,
            log_level=options["log_level"],
            access_log=options["access_log"],
        )


def parse_addr(addr: str) -> tuple[str, int]:
    if addr.isdecimal():
        host, port = "127.0.0.1", int(addr)
    elif addr.startswith("["):
        closing_bracket = addr.find("]")
        if (
            closing_bracket == -1
            or addr[closing_bracket + 1 : closing_bracket + 2] != ":"
        ):
            raise CommandError(f"Invalid address: {addr}")
        host = addr[1:closing_bracket]
        port_str = addr[closing_bracket + 2 :]
        if not host or not port_str.isdecimal():
            raise CommandError(f"Invalid address: {addr}")
        port = int(port_str)
    else:
        try:
            host, port_str = addr.rsplit(":", 1)
        except Exception as e:
            raise CommandError(f"Invalid address: {addr}") from e

        if not host or not port_str.isdecimal():
            raise CommandError(f"Invalid address: {addr}")
        port = int(port_str)

    if not 1 <= port <= 65535:
        raise CommandError(f"Invalid port: {port}")
    if host == "0":
        host = "0.0.0.0"
    return host, port
