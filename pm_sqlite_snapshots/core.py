import gzip
import hashlib
import importlib
import json
import os
import shutil
import socket
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone

from django.conf import settings as django_settings
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder

from .settings import SnapshotSettings


class SnapshotError(Exception):
    pass


def export_snapshot(config: SnapshotSettings, reason: str = "manual"):
    db_path = get_sqlite_database_path(config.database_alias)
    storage = load_storage(config)
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    with export_lock(config.lock_path):
        with tempfile.TemporaryDirectory(prefix="pm_sqlite_snapshot_") as tmpdir:
            backup_path = os.path.join(tmpdir, f"{snapshot_id}.sqlite3")
            compressed_path = f"{backup_path}.gz"
            _backup_sqlite(db_path, backup_path)
            _gzip_file(backup_path, compressed_path)
            manifest = _build_manifest(
                snapshot_id=snapshot_id,
                db_path=db_path,
                backup_path=backup_path,
                compressed_path=compressed_path,
                reason=reason,
                config=config,
            )
            return storage.upload(compressed_path, manifest)


def restore_snapshot(config: SnapshotSettings, snapshot_id: str | None = None, force: bool = False):
    db_path = get_sqlite_database_path(config.database_alias)
    storage = load_storage(config)
    snapshot = _select_snapshot(storage, snapshot_id)
    if snapshot is None:
        raise SnapshotError("No SQLite snapshot is available to restore")
    if os.path.exists(db_path) and not force:
        raise SnapshotError(f"Database already exists at {db_path}; pass force=True to replace it")

    with export_lock(config.lock_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pm_sqlite_restore_") as tmpdir:
            compressed_path = os.path.join(tmpdir, "restore.sqlite3.gz")
            restored_path = os.path.join(tmpdir, "restore.sqlite3")
            storage.download(snapshot, compressed_path)
            if snapshot.sha256:
                actual_sha = sha256_file(compressed_path)
                if actual_sha != snapshot.sha256:
                    raise SnapshotError(
                        f"Snapshot checksum mismatch: expected {snapshot.sha256}, got {actual_sha}"
                    )
            _gunzip_file(compressed_path, restored_path)
            _validate_sqlite(restored_path)
            replacement_path = f"{db_path}.restore_tmp"
            shutil.copy2(restored_path, replacement_path)
            connections.close_all()
            os.replace(replacement_path, db_path)
    return snapshot


def list_snapshots(config: SnapshotSettings):
    return load_storage(config).list()


def prune_snapshots(config: SnapshotSettings):
    keep_last = int(config.retention.get("KEEP_LAST", 20))
    storage = load_storage(config)
    latest = storage.latest()
    deleted = []
    for snapshot in storage.list()[keep_last:]:
        if latest and snapshot.snapshot_id == latest.snapshot_id:
            continue
        storage.delete(snapshot)
        deleted.append(snapshot)
    return deleted


def get_sqlite_database_path(alias: str):
    db_config = connections.databases[alias]
    engine = db_config.get("ENGINE", "")
    if engine != "django.db.backends.sqlite3":
        raise SnapshotError(f"Database alias {alias!r} is not using SQLite: {engine}")
    db_path = db_config.get("NAME")
    if not db_path or db_path == ":memory:":
        raise SnapshotError("SQLite snapshot export requires a filesystem database path")
    return os.path.abspath(db_path)


def load_storage(config: SnapshotSettings):
    storage_config = dict(config.storage)
    backend = storage_config.pop("BACKEND", "")
    if not backend:
        raise SnapshotError("SQLITE_SNAPSHOTS STORAGE.BACKEND is required")
    module_name, class_name = backend.rsplit(".", 1)
    cls = getattr(importlib.import_module(module_name), class_name)
    if hasattr(cls, "from_config"):
        return cls.from_config(storage_config)
    return cls(**storage_config)


@contextmanager
def export_lock(lock_path: str):
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_file = open(lock_path, "w", encoding="utf-8")
    try:
        _lock_file(lock_file)
        yield
    finally:
        _unlock_file(lock_file)
        lock_file.close()


def sha256_file(path: str):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_sqlite(db_path: str, backup_path: str):
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _gzip_file(source_path: str, compressed_path: str):
    with open(source_path, "rb") as source, gzip.open(compressed_path, "wb") as target:
        shutil.copyfileobj(source, target)


def _gunzip_file(compressed_path: str, destination_path: str):
    with gzip.open(compressed_path, "rb") as source, open(destination_path, "wb") as target:
        shutil.copyfileobj(source, target)


def _validate_sqlite(path: str):
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if not result or result[0] != "ok":
        raise SnapshotError(f"Restored SQLite database failed integrity_check: {result}")


def _build_manifest(
    *,
    snapshot_id: str,
    db_path: str,
    backup_path: str,
    compressed_path: str,
    reason: str,
    config: SnapshotSettings,
):
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "snapshot_id": snapshot_id,
        "created_at": created_at,
        "reason": reason,
        "database_alias": config.database_alias,
        "database_path": db_path,
        "compressed_size_bytes": os.path.getsize(compressed_path),
        "uncompressed_size_bytes": os.path.getsize(backup_path),
        "sha256": sha256_file(compressed_path),
        "django_migrations": _migration_state(),
        "source": {
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "git_sha": getattr(django_settings, "GIT_SHA", os.environ.get("GIT_SHA", "")),
        },
    }


def _migration_state():
    try:
        migrations = MigrationRecorder.Migration.objects.values_list("app", "name")
        return {app: name for app, name in migrations}
    except Exception:
        return {}


def _select_snapshot(storage, snapshot_id: str | None):
    if not snapshot_id:
        return storage.latest()
    for snapshot in storage.list():
        if snapshot.snapshot_id == snapshot_id:
            return snapshot
    return None


def _lock_file(lock_file):
    try:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    except ImportError:
        return


def _unlock_file(lock_file):
    try:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except ImportError:
        return
