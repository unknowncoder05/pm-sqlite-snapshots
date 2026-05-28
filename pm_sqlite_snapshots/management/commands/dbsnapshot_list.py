from django.core.management.base import BaseCommand

from pm_sqlite_snapshots.core import list_snapshots
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "List SQLite database snapshots."

    def handle(self, *args, **options):
        for snapshot in list_snapshots(get_snapshot_settings()):
            self.stdout.write(
                f"{snapshot.snapshot_id}\t{snapshot.created_at}\t{snapshot.database_key}"
            )
