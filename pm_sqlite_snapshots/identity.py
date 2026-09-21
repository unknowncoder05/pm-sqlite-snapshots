from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from .core import SnapshotError, export_lock, get_sqlite_database_path, load_storage, restore_snapshot


def _identity_digest(config):
    storage = config.storage
    backend = storage.get('BACKEND', '')
    if backend.endswith('S3SnapshotStorage'):
        location = (storage.get('BUCKET'), storage.get('PREFIX'))
    elif backend.endswith('LocalSnapshotStorage'):
        location = (os.path.abspath(storage.get('PATH', '')), storage.get('PREFIX', ''))
    else:
        raise SnapshotError('Unsupported snapshot storage identity')
    if any(value is None or not str(value).strip() for value in location):
        raise SnapshotError('Snapshot storage identity is incomplete')
    payload = json.dumps((backend, *location), separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def write_identity_receipt(config):
    db_path = get_sqlite_database_path(config.database_alias)
    digest = _identity_digest(config)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS pm_snapshot_identity (digest TEXT NOT NULL)')
        connection.execute('DELETE FROM pm_snapshot_identity')
        connection.execute('INSERT INTO pm_snapshot_identity (digest) VALUES (?)', (digest,))
        connection.commit()
    finally:
        connection.close()


def verify_identity_receipt(config):
    db_path = get_sqlite_database_path(config.database_alias)
    connection = sqlite3.connect(db_path)
    try:
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise SnapshotError('SQLite database integrity check failed')
        try:
            rows = connection.execute('SELECT digest FROM pm_snapshot_identity').fetchall()
        except sqlite3.DatabaseError as exc:
            raise SnapshotError('SQLite snapshot identity receipt is missing') from exc
        if rows != [(_identity_digest(config),)]:
            raise SnapshotError('SQLite snapshot identity receipt does not match storage')
    finally:
        connection.close()


def prepare_snapshot_startup(config):
    if not (config.enabled and config.restore_on_startup and config.require_identity_receipt):
        return
    db_path = get_sqlite_database_path(config.database_alias)
    with export_lock(f'{db_path}.startup.lock'):
        if load_storage(config).latest() is None:
            raise SnapshotError('No SQLite snapshot is available for startup')
        if not os.path.exists(db_path):
            restore_snapshot(config)
        verify_identity_receipt(config)
