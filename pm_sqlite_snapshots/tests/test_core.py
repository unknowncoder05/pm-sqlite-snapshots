import os
import sqlite3

import django
import pytest
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

from pm_sqlite_snapshots.core import SnapshotError, export_snapshot, list_snapshots, prune_snapshots, restore_snapshot
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


def test_restore_rejects_checksum_mismatch(tmp_path):
    db_path = tmp_path / "app.sqlite3"
    storage_path = tmp_path / "snapshots"
    _write_database(db_path, "before")
    config = _config(tmp_path, db_path, storage_path)

    with override_settings(
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}}
    ):
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
        first = export_snapshot(config, reason="first")
        _insert_value(db_path, "second")
        second = export_snapshot(config, reason="second")

        deleted = prune_snapshots(config)
        remaining_ids = {snapshot.snapshot_id for snapshot in list_snapshots(config)}

        assert [snapshot.snapshot_id for snapshot in deleted] == [first.snapshot_id]
        assert remaining_ids == {second.snapshot_id}


def _write_database(path, value):
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def _insert_value(path, value):
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM sample")
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


def _config(tmp_path, db_path, storage_path, keep_last=20):
    return SnapshotSettings(
        enabled=True,
        database_alias="default",
        interval_seconds=0,
        export_on_shutdown=False,
        restore_on_startup=False,
        restore_if_db_missing=True,
        fail_startup_if_restore_missing=False,
        lock_path=str(tmp_path / "snapshot.lock"),
        storage={
            "BACKEND": "pm_sqlite_snapshots.storage.local.LocalSnapshotStorage",
            "PATH": str(storage_path),
        },
        retention={"KEEP_LAST": keep_last},
    )
