from django.core.management.base import BaseCommand

from pm_sqlite_snapshots.identity import prepare_snapshot_startup
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Verify or restore the bound SQLite snapshot before migrations."

    def handle(self, *args, **options):
        prepare_snapshot_startup(get_snapshot_settings())
