from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import Guest
from api.services.avatar import AvatarService, AvatarTransferError


class Command(BaseCommand):
    help = "Mirror external guest avatars into object storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview guests to sync without modifying storage or database.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-sync even if Guest.avatar already uses managed storage.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of guests to process (0 means unlimited).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        force: bool = options["force"]
        limit: int = options["limit"]
        if limit < 0:
            raise CommandError("--limit must be non-negative")

        service = AvatarService()
        queryset = Guest.objects.order_by("created_at", "pk")

        attempted = 0
        synced = 0
        skipped = 0
        failed = 0

        for guest in queryset.iterator():
            if limit > 0 and attempted >= limit:
                break

            already_managed = service.is_managed_url(guest.avatar)
            if already_managed and not force:
                skipped += 1
                continue

            source_url = guest.avatar_source_url or (
                "" if already_managed else guest.avatar
            )
            if not source_url:
                skipped += 1
                continue

            attempted += 1
            if dry_run:
                self.stdout.write(f"[dry-run] {guest.pk} ({guest.name}): {source_url}")
                synced += 1
                continue

            expected_avatar = guest.avatar
            expected_source_url = guest.avatar_source_url
            try:
                mirrored_url = service.mirror(source_url)
            except AvatarTransferError as exc:
                failed += 1
                self.stderr.write(
                    self.style.WARNING(f"Failed {guest.pk} ({guest.name}): {exc}")
                )
                continue

            updated = Guest.objects.filter(
                pk=guest.pk,
                avatar=expected_avatar,
                avatar_source_url=expected_source_url,
            ).update(
                avatar=mirrored_url,
                avatar_source_url=source_url,
                updated_at=timezone.now(),
            )
            if not updated:
                skipped += 1
                continue

            synced += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Synced {guest.pk} ({guest.name}) -> {mirrored_url}"
                )
            )

        self.stdout.write(f"Done. synced={synced}, skipped={skipped}, failed={failed}")
