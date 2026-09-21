import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import django
import pytest
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connections
from django.test import override_settings

if not settings.configured:
    settings.configure(
        SECRET_KEY='test',
        INSTALLED_APPS=['django.contrib.contenttypes'],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    )
django.setup()

from pm_sqlite_snapshots.management.commands.dbsnapshot_bootstrap import Command
from pm_sqlite_snapshots.management.commands.dbsnapshot_adopt_legacy import Command as AdoptLegacyCommand
from pm_sqlite_snapshots.core import export_snapshot
from pm_sqlite_snapshots.identity import prepare_snapshot_startup
from pm_sqlite_snapshots.settings import get_snapshot_settings


def _snapshot_settings(tmp_path):
    return {
        'ENABLED': True,
        'DATABASE_ALIAS': 'default',
        'RESTORE_ON_STARTUP': True,
        'FAIL_STARTUP_IF_RESTORE_MISSING': True,
        'REQUIRE_IDENTITY_RECEIPT': True,
        'LOCK_PATH': str(tmp_path / 'export.lock'),
        'STORAGE': {
            'BACKEND': 'pm_sqlite_snapshots.storage.local.LocalSnapshotStorage',
            'PATH': str(tmp_path / 'snapshots'),
            'PREFIX': 'fixed-project/sqlite/',
        },
    }


def test_bootstrap_command_exports_once_and_refuses_repeat(tmp_path):
    database = tmp_path / 'app.sqlite3'
    connections.close_all()
    connections.databases['default'].update(
        {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(database)}
    )
    with override_settings(SQLITE_SNAPSHOTS=_snapshot_settings(tmp_path)):
        Command().handle()
        assert database.exists()
        assert (tmp_path / 'snapshots/latest.json').exists()
        with pytest.raises(CommandError, match='already exists'):
            Command().handle()


def test_bootstrap_command_refuses_existing_application_data(tmp_path):
    database = tmp_path / 'app.sqlite3'
    connections.close_all()
    connections.databases['default'].update(
        {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(database)}
    )
    connection = sqlite3.connect(str(database))
    try:
        connection.execute('CREATE TABLE content (value text)')
        connection.execute("INSERT INTO content VALUES ('existing')")
        connection.commit()
    finally:
        connection.close()
    with override_settings(SQLITE_SNAPSHOTS=_snapshot_settings(tmp_path)):
        with pytest.raises(CommandError, match='Existing application data'):
            Command().handle()
        assert not (tmp_path / 'snapshots/latest.json').exists()


def test_manage_py_bootstrap_runs_before_runtime_restore(tmp_path):
    fixture = Path(__file__).parent / 'bootstrap_fixture'
    package_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update({
        'BOOTSTRAP_TEST_DB': str(tmp_path / 'app.sqlite3'),
        'BOOTSTRAP_TEST_STORE': str(tmp_path / 'snapshots'),
        'PYTHONPATH': os.pathsep.join((str(fixture), str(package_root), env.get('PYTHONPATH', ''))),
    })
    command = [sys.executable, str(fixture / 'manage.py'), 'dbsnapshot_bootstrap']
    first = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert (tmp_path / 'snapshots/latest.json').exists()
    second = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert second.returncode != 0
    assert 'Snapshot already exists' in second.stderr

    os.remove(env['BOOTSTRAP_TEST_DB'])
    prepare = subprocess.run(
        [sys.executable, str(fixture / 'manage.py'), 'dbsnapshot_prepare_startup'],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert prepare.returncode == 0, prepare.stderr
    assert Path(env['BOOTSTRAP_TEST_DB']).exists()

    os.remove(env['BOOTSTRAP_TEST_DB'])
    runtime = subprocess.run(
        [sys.executable, '-c', "import os; os.environ['DJANGO_SETTINGS_MODULE']='bootstrap_settings'; import django; django.setup()"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert runtime.returncode == 0, runtime.stderr
    assert Path(env['BOOTSTRAP_TEST_DB']).exists()

    os.remove(env['BOOTSTRAP_TEST_DB'])
    migrated_first = subprocess.run(
        [sys.executable, str(fixture / 'manage.py'), 'migrate', '--noinput'],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert migrated_first.returncode == 0, migrated_first.stderr
    rejected = subprocess.run(
        [sys.executable, str(fixture / 'manage.py'), 'dbsnapshot_prepare_startup'],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert rejected.returncode != 0
    assert 'identity receipt is missing' in rejected.stderr


def test_legacy_adoption_requires_verified_snapshot_and_missing_database(tmp_path):
    database = tmp_path / 'app.sqlite3'
    connections.close_all()
    connections.databases['default'].update(
        {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(database)}
    )
    connection = sqlite3.connect(str(database))
    try:
        connection.execute('CREATE TABLE content (value text)')
        connection.execute("INSERT INTO content VALUES ('legacy')")
        connection.commit()
    finally:
        connection.close()
    with override_settings(SQLITE_SNAPSHOTS=_snapshot_settings(tmp_path)):
        config = get_snapshot_settings()
        old = export_snapshot(config, reason='legacy')
        os.remove(str(database))
        with pytest.raises(CommandError, match='checksum'):
            AdoptLegacyCommand().handle(snapshot_id=old.snapshot_id, expected_sha256='0' * 64)
        assert not database.exists()
        AdoptLegacyCommand().handle(snapshot_id=old.snapshot_id, expected_sha256=old.sha256)
        prepare_snapshot_startup(config)
        connection = sqlite3.connect(str(database))
        try:
            assert connection.execute('SELECT value FROM content').fetchone() == ('legacy',)
        finally:
            connection.close()
        with pytest.raises(CommandError, match='missing destination'):
            AdoptLegacyCommand().handle(snapshot_id=old.snapshot_id, expected_sha256=old.sha256)
