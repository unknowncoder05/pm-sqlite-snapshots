from django.core.management.base import BaseCommand

from pm_sqlite_snapshots.core import export_snapshot
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Export the configured SQLite database to snapshot storage."

    def add_arguments(self, parser):
        parser.add_argument("--reason", default="manual")

    def handle(self, *args, **options):
        snapshot = export_snapshot(get_snapshot_settings(), reason=options["reason"])
        self.stdout.write(self.style.SUCCESS(f"Exported snapshot {snapshot.snapshot_id}"))
