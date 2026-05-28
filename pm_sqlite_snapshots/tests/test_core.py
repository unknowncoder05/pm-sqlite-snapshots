import os
import sqlite3

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        SECRET_KEY="test",
        INSTALLED_APPS=["django.contrib.contenttypes"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
        USE_TZ=True,
    )
    django.setup()

from django.test import override_settings

from pm_sqlite_snapshots.core import export_snapshot, list_snapshots, restore_snapshot
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
        snapshot = export_snapshot(config, reason="test")
        os.remove(db_path)
        restore_snapshot(config, snapshot_id=snapshot.snapshot_id, force=True)

        assert _read_value(db_path) == "before"
        assert list_snapshots(config)[0].snapshot_id == snapshot.snapshot_id


def _write_database(path, value):
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def _read_value(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM sample").fetchone()[0]
    finally:
        conn.close()
