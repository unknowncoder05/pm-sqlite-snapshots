from django.core.management.base import BaseCommand

from pm_sqlite_snapshots.core import restore_snapshot
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Restore a SQLite database snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id")
        parser.add_argument("--latest", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        snapshot_id = None if options["latest"] else options.get("snapshot_id")
        snapshot = restore_snapshot(get_snapshot_settings(), snapshot_id=snapshot_id, force=options["force"])
        self.stdout.write(self.style.SUCCESS(f"Restored snapshot {snapshot.snapshot_id}"))
