from django.core.management import BaseCommand
from django.db import transaction

from api.models import ApiClient


class Command(BaseCommand):
    help = "Re-encrypt API client secrets with the current Fernet key"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only show how many clients would be re-encrypted, without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        qs = ApiClient.objects.exclude(secret="")
        count = 0

        if dry_run:
            count = qs.count()
            self.stdout.write(f"Dry-run: {count} API client(s) would be re-encrypted.")
            return

        with transaction.atomic():
            for client in qs.iterator():
                client.secret = client.secret
                client.save(update_fields=["secret"])
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {count} API client(s)."))
