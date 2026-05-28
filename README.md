# pm-sqlite-snapshots

Small Django app for running SQLite on ephemeral compute while exporting durable
database snapshots to object storage.

It is intended for single-writer preview/demo deployments. Use RDS/PostgreSQL for
multi-replica or high-value production data.

## Install

```txt
pm-sqlite-snapshots @ git+https://github.com/unknowncoder05/pm-sqlite-snapshots.git
```

```python
INSTALLED_APPS += ["pm_sqlite_snapshots.apps.SQLiteSnapshotsConfig"]
```

## Settings

```python
SQLITE_SNAPSHOTS = {
    "ENABLED": True,
    "DATABASE_ALIAS": "default",
    "INTERVAL_SECONDS": 300,
    "EXPORT_ON_SHUTDOWN": True,
    "RESTORE_ON_STARTUP": True,
    "RESTORE_IF_DB_MISSING": True,
    "FAIL_STARTUP_IF_RESTORE_MISSING": False,
    "LOCK_PATH": "/tmp/pm_sqlite_snapshots.lock",
    "STORAGE": {
        "BACKEND": "pm_sqlite_snapshots.storage.s3.S3SnapshotStorage",
        "BUCKET": "my-snapshot-bucket",
        "PREFIX": "app/sqlite/",
        "REGION": "us-east-1",
        "SERVER_SIDE_ENCRYPTION": "aws:kms",
        "KMS_KEY_ID": "alias/my-snapshot-key",
    },
    "RETENTION": {
        "KEEP_LAST": 20,
    },
}
```

## Commands

```bash
python manage.py dbsnapshot_export
python manage.py dbsnapshot_restore --latest
python manage.py dbsnapshot_list
python manage.py dbsnapshot_prune
```
