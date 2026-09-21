from django.core.management.base import BaseCommand, CommandError

from pm_sqlite_snapshots.core import restore_snapshot, restore_snapshot_if_missing
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Restore a SQLite database snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id")
        parser.add_argument("--latest", action="store_true")
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--if-missing", action="store_true", help="Skip if another process restored the database")

    def handle(self, *args, **options):
        snapshot_id = None if options["latest"] else options.get("snapshot_id")
        if options["if_missing"] and options["force"]:
            raise CommandError("--if-missing and --force cannot be combined")
        if options["if_missing"]:
            snapshot = restore_snapshot_if_missing(get_snapshot_settings(), snapshot_id=snapshot_id)
            if snapshot is None:
                self.stdout.write("Database already exists; skipped snapshot restore")
                return
        else:
            snapshot = restore_snapshot(get_snapshot_settings(), snapshot_id=snapshot_id, force=options["force"])
        self.stdout.write(self.style.SUCCESS(f"Restored snapshot {snapshot.snapshot_id}"))
