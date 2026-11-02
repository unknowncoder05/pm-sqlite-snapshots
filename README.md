# pm-sqlite-snapshots

Small Django app for running SQLite on ephemeral compute while exporting durable
database snapshots to object storage.

It is intended for single-writer preview/demo deployments. Use RDS/PostgreSQL for
multi-replica or high-value production data.

## Install

```txt
pm-sqlite-snapshots @ git+https://github.com/unknowncoder05/pm-sqlite-snapshots.git@9ee6423665cfa86890b31300792e39c11a458afb
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
    "FAIL_STARTUP_IF_RESTORE_MISSING": True,
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
python manage.py dbsnapshot_bootstrap
python manage.py dbsnapshot_adopt_legacy --snapshot-id ID --expected-sha256 SHA256
python manage.py dbsnapshot_restore --latest
python manage.py dbsnapshot_list
python manage.py dbsnapshot_prune
```

For a new deployment with no snapshot, run `dbsnapshot_bootstrap` once before
starting the web process. The command checks storage directly, applies
migrations, and exports the first snapshot. Verify that `dbsnapshot_list` shows
the new snapshot. Subsequent starts restore normally; do not leave a permissive
restore setting in the deployment environment. Never bootstrap an existing
project whose snapshots are missing or inaccessible: recover its original
storage identity and snapshot instead.

Existing deployments whose snapshots predate the identity receipt require an
operator-reviewed migration. Pause writers; retain the original bucket and
prefix; verify the chosen snapshot ID, SHA-256, and application records against
the original backup. On a fresh, empty database path, run
`dbsnapshot_adopt_legacy --snapshot-id ID --expected-sha256 SHA256`. It restores
the selected archive with checksum validation, writes the receipt, and exports
a new snapshot. Confirm the new snapshot exists before resuming services. Never
adopt by changing the namespace or over an existing database.
