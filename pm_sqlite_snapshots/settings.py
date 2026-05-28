from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class SnapshotSettings:
    enabled: bool
    database_alias: str
    interval_seconds: int
    export_on_shutdown: bool
    restore_on_startup: bool
    restore_if_db_missing: bool
    fail_startup_if_restore_missing: bool
    lock_path: str
    storage: dict[str, Any]
    retention: dict[str, Any]


def get_snapshot_settings() -> SnapshotSettings:
    raw = getattr(settings, "SQLITE_SNAPSHOTS", {}) or {}
    return SnapshotSettings(
        enabled=bool(raw.get("ENABLED", False)),
        database_alias=raw.get("DATABASE_ALIAS", "default"),
        interval_seconds=int(raw.get("INTERVAL_SECONDS", 300)),
        export_on_shutdown=bool(raw.get("EXPORT_ON_SHUTDOWN", True)),
        restore_on_startup=bool(raw.get("RESTORE_ON_STARTUP", False)),
        restore_if_db_missing=bool(raw.get("RESTORE_IF_DB_MISSING", True)),
        fail_startup_if_restore_missing=bool(raw.get("FAIL_STARTUP_IF_RESTORE_MISSING", False)),
        lock_path=raw.get("LOCK_PATH", "/tmp/pm_sqlite_snapshots.lock"),
        storage=raw.get("STORAGE", {}),
        retention=raw.get("RETENTION", {"KEEP_LAST": 20}),
    )
