from dataclasses import replace
import os
import sqlite3

import django
import pytest
from django.conf import settings
from django.db import connections
from django.test import override_settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        INSTALLED_APPS=['django.contrib.contenttypes'],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    )
django.setup()

from pm_sqlite_snapshots.core import SnapshotError, export_snapshot
from pm_sqlite_snapshots.identity import prepare_snapshot_startup
from pm_sqlite_snapshots.management.commands.dbsnapshot_bootstrap import Command
from pm_sqlite_snapshots.settings import get_snapshot_settings


def test_explicit_bootstrap_then_replacement_and_changed_namespace(tmp_path):
    database = tmp_path / 'app.sqlite3'
    connections.close_all()
    connections.databases['default'].update(
        {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(database)}
    )
    raw = {
        'ENABLED': True,
        'RESTORE_ON_STARTUP': True,
        'FAIL_STARTUP_IF_RESTORE_MISSING': True,
        'REQUIRE_IDENTITY_RECEIPT': True,
        'LOCK_PATH': str(tmp_path / 'snapshot.lock'),
        'STORAGE': {
            'BACKEND': 'pm_sqlite_snapshots.storage.local.LocalSnapshotStorage',
            'PATH': str(tmp_path / 'original_namespace'),
            'PREFIX': 'fixed-project/sqlite/',
        },
    }

    with override_settings(SQLITE_SNAPSHOTS=raw):
        config = get_snapshot_settings()
        with pytest.raises(SnapshotError, match='No SQLite snapshot'):
            prepare_snapshot_startup(config)
        assert not database.exists()
        Command().handle()

    connection = sqlite3.connect(str(database))
    try:
        connection.execute('CREATE TABLE content (value text)')
        connection.execute("INSERT INTO content VALUES ('original')")
        connection.commit()
    finally:
        connection.close()

    connection = sqlite3.connect(str(database))
    try:
        connection.execute("UPDATE content SET value = 'periodic'")
        connection.commit()
    finally:
        connection.close()
    export_snapshot(config, reason='periodic')

    os.remove(str(database))
    prepare_snapshot_startup(config)
    connection = sqlite3.connect(str(database))
    try:
        assert connection.execute('SELECT value FROM content').fetchone() == ('periodic',)
    finally:
        connection.close()

    changed_prefix = replace(config, storage={**config.storage, 'PREFIX': 'changed/sqlite/'})
    with pytest.raises(SnapshotError, match='does not match storage'):
        prepare_snapshot_startup(changed_prefix)

    os.remove(str(database))
    changed_namespace = replace(config, storage={**config.storage, 'PATH': str(tmp_path / 'changed_namespace')})
    with pytest.raises(SnapshotError, match='No SQLite snapshot'):
        prepare_snapshot_startup(changed_namespace)
    assert not database.exists()
