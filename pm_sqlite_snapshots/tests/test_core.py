import os
import sqlite3

import django
import pytest
from django.conf import settings
from django.db import connections

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        INSTALLED_APPS=["django.contrib.contenttypes"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        USE_TZ=True,
    )
    django.setup()

from django.test import override_settings

from pm_sqlite_snapshots.apps import _is_management_command_without_runtime_hooks
from pm_sqlite_snapshots.core import SnapshotError, export_snapshot, list_snapshots, prune_snapshots, restore_snapshot
from pm_sqlite_snapshots.runtime import maybe_restore_on_startup
from pm_sqlite_snapshots.settings import SnapshotSettings


def test_export_and_restore_sqlite_snapshot_with_local_storage(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    lock_path = tmp_path / "snapshot.lock"

    _write_database(db_path, "before")
    config = SnapshotSettings(
        enabled=True,
        database_alias="default",
        interval_seconds=0,
        export_on_shutdown=False,
        restore_on_startup=False,
        restore_if_db_missing=True,
        restore_if_db_empty=True,
        fail_startup_if_restore_missing=False,
        lock_path=str(lock_path),
        storage={
            "BACKEND": "pm_sqlite_snapshots.storage.local.LocalSnapshotStorage",
            "PATH": str(storage_path),
        },
        retention={"KEEP_LAST": 20},
    )

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
        _set_database_path(db_path)
        snapshot = export_snapshot(config, reason="test")
        os.remove(db_path)
        restore_snapshot(config, snapshot_id=snapshot.snapshot_id, force=True)

        assert _read_value(db_path) == "before"
        assert list_snapshots(config)[0].snapshot_id == snapshot.snapshot_id


def test_restore_rejects_checksum_mismatch(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    _write_database(db_path, "before")
    config = _config(tmp_path, db_path, storage_path)

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
        _set_database_path(db_path)
        snapshot = export_snapshot(config, reason="test")
        latest_path = storage_path / "latest.json"
        latest_path.write_text(latest_path.read_text().replace(snapshot.sha256, "0" * 64))
        os.remove(db_path)

        with pytest.raises(SnapshotError, match="checksum mismatch"):
            restore_snapshot(config, force=True)


def test_prune_keeps_latest_snapshot_even_when_outside_keep_window(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    _write_database(db_path, "first")
    config = _config(tmp_path, db_path, storage_path, keep_last=1)

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
        _set_database_path(db_path)
        first = export_snapshot(config, reason="first")
        _insert_value(db_path, "second")
        second = export_snapshot(config, reason="second")

        deleted = prune_snapshots(config)
        remaining_ids = {snapshot.snapshot_id for snapshot in list_snapshots(config)}

        assert [snapshot.snapshot_id for snapshot in deleted] == [first.snapshot_id]
        assert remaining_ids == {second.snapshot_id}


def test_restore_on_startup_replaces_migration_only_database(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    _write_database(db_path, "snapshot")
    config = _config(tmp_path, db_path, storage_path)
    config = SnapshotSettings(
        **{**config.__dict__, "restore_on_startup": True, "restore_if_db_missing": True, "restore_if_db_empty": True}
    )

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
        _set_database_path(db_path)
        export_snapshot(config, reason="test")
        os.remove(db_path)
        _write_migration_only_database(db_path)

        maybe_restore_on_startup(config)

        assert _read_value(db_path) == "snapshot"


def test_restore_on_startup_does_not_replace_database_with_application_data(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    _write_database(db_path, "snapshot")
    config = _config(tmp_path, db_path, storage_path)
    config = SnapshotSettings(
        **{**config.__dict__, "restore_on_startup": True, "restore_if_db_missing": True, "restore_if_db_empty": True}
    )

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
        _set_database_path(db_path)
        export_snapshot(config, reason="test")
        _write_database(db_path, "current")

        maybe_restore_on_startup(config)

        assert _read_value(db_path) == "current"


def test_gunicorn_process_uses_runtime_hooks(monkeypatch):
    monkeypatch.setattr("sys.argv", ["/usr/local/bin/gunicorn", "config.wsgi:application"])

    assert _is_management_command_without_runtime_hooks() is False


def _write_database(path, value):
    connections.close_all()
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def _insert_value(path, value):
    connections.close_all()
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM sample")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def _read_value(path):
    connections.close_all()
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM sample").fetchone()[0]
    finally:
        conn.close()


def _write_migration_only_database(path):
    connections.close_all()
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE django_migrations (id integer primary key, app text, name text, applied text)")
        conn.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('auth', '0001_initial', 'now')")
        conn.execute("CREATE TABLE auth_permission (id integer primary key, name text)")
        conn.execute("INSERT INTO auth_permission (name) VALUES ('Can add user')")
        conn.commit()
    finally:
        conn.close()


def _set_database_path(path):
    connections.databases["default"].update(
        {"ENGINE": "django.db.backends.sqlite3", "NAME": str(path)}
    )


def _config(tmp_path, db_path, storage_path, keep_last=20):
    return SnapshotSettings(
        enabled=True,
        database_alias="default",
        interval_seconds=0,
        export_on_shutdown=False,
        restore_on_startup=False,
        restore_if_db_missing=True,
        restore_if_db_empty=True,
        fail_startup_if_restore_missing=False,
        lock_path=str(tmp_path / "snapshot.lock"),
        storage={
            "BACKEND": "pm_sqlite_snapshots.storage.local.LocalSnapshotStorage",
            "PATH": str(storage_path),
        },
        retention={"KEEP_LAST": keep_last},
    )
