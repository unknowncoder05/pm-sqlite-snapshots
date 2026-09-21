import os

from django.core.management.base import BaseCommand, CommandError

from pm_sqlite_snapshots.core import (
    export_lock, export_snapshot, get_sqlite_database_path, load_storage, restore_snapshot,
)
from pm_sqlite_snapshots.identity import write_identity_receipt
from pm_sqlite_snapshots.settings import get_snapshot_settings


class Command(BaseCommand):
    help = "Adopt a verified legacy snapshot onto a missing SQLite database."

    def add_arguments(self, parser):
        parser.add_argument('--snapshot-id', required=True)
        parser.add_argument('--expected-sha256', required=True)

    def handle(self, *args, **options):
        config = get_snapshot_settings()
        if not config.enabled:
            raise CommandError('SQLite snapshots must be enabled')
        db_path = get_sqlite_database_path(config.database_alias)
        with export_lock(f'{db_path}.startup.lock'):
            if os.path.exists(db_path):
                raise CommandError('Legacy adoption requires a missing destination database')
            selected = next((ref for ref in load_storage(config).list()
                             if ref.snapshot_id == options['snapshot_id']), None)
            expected = options['expected_sha256'].lower()
            if selected is None or not selected.sha256 or selected.sha256.lower() != expected:
                raise CommandError('Legacy snapshot ID or checksum does not match storage')
            restore_snapshot(config, snapshot_id=selected.snapshot_id)
            write_identity_receipt(config)
            snapshot = export_snapshot(config, reason='legacy-adoption')
        self.stdout.write(self.style.SUCCESS(f'Adopted snapshot {snapshot.snapshot_id}'))
