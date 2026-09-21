import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from pm_sqlite_snapshots.core import (
    export_lock,
    export_snapshot,
    get_sqlite_database_path,
    load_storage,
)
from pm_sqlite_snapshots.runtime import _database_has_application_data
from pm_sqlite_snapshots.identity import write_identity_receipt
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Initialize the first SQLite snapshot for a new project only."

    def handle(self, *args, **options):
        config = get_snapshot_settings()
        if not config.enabled:
            raise CommandError("SQLite snapshots must be enabled before bootstrap")
        db_path = get_sqlite_database_path(config.database_alias)
        with export_lock(f"{db_path}.startup.lock"):
            if load_storage(config).latest() is not None:
                raise CommandError("Snapshot already exists; bootstrap is only for a new project")
            if os.path.exists(db_path) and _database_has_application_data(db_path):
                raise CommandError("Existing application data cannot be bootstrapped as a new project")
            call_command('migrate', database=config.database_alias, interactive=False, verbosity=0)
            write_identity_receipt(config)
            snapshot = export_snapshot(config, reason='bootstrap')
        self.stdout.write(self.style.SUCCESS(f"Initialized snapshot {snapshot.snapshot_id}"))
