from django.core.management.base import BaseCommand

from pm_sqlite_snapshots.core import prune_snapshots
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Prune old SQLite database snapshots according to SQLITE_SNAPSHOTS retention settings."

    def handle(self, *args, **options):
        deleted = prune_snapshots(get_snapshot_settings())
        for snapshot in deleted:
            self.stdout.write(f"Deleted {snapshot.snapshot_id}")
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(deleted)} snapshots"))
