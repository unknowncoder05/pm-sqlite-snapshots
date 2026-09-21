import pytest
from django.conf import settings
from django.test import override_settings

if not settings.configured:
    settings.configure(SECRET_KEY="test")

from pm_sqlite_snapshots.settings import get_snapshot_settings
from pm_sqlite_snapshots.identity import _identity_digest, prepare_snapshot_startup
from pm_sqlite_snapshots.core import SnapshotError


def test_enabled_snapshots_reject_unrendered_storage_prefix():
    with override_settings(SQLITE_SNAPSHOTS={
        "ENABLED": True,
        "STORAGE": {"PREFIX": "{{project_slug}}/sqlite/"},
    }):
        with pytest.raises(ValueError, match="rendered, stable identity"):
            get_snapshot_settings()


def test_package_defaults_preserve_optional_export_only_usage():
    with override_settings(SQLITE_SNAPSHOTS={
        "ENABLED": True,
        "STORAGE": {"PREFIX": "fixed-project/sqlite/"},
    }):
        config = get_snapshot_settings()
        assert config.fail_startup_if_restore_missing is False
        assert config.require_identity_receipt is False
        prepare_snapshot_startup(config)


def test_export_only_opt_out_skips_receipt_preflight():
    with override_settings(SQLITE_SNAPSHOTS={
        'ENABLED': True,
        'RESTORE_ON_STARTUP': False,
        'FAIL_STARTUP_IF_RESTORE_MISSING': False,
        'REQUIRE_IDENTITY_RECEIPT': True,
        'STORAGE': {},
    }):
        prepare_snapshot_startup(get_snapshot_settings())


def test_missing_snapshot_bucket_is_not_a_storage_identity():
    with override_settings(SQLITE_SNAPSHOTS={
        'ENABLED': True,
        'STORAGE': {'BACKEND': 'pm_sqlite_snapshots.storage.s3.S3SnapshotStorage',
                    'BUCKET': None, 'PREFIX': 'fixed/sqlite/'},
    }):
        with pytest.raises(SnapshotError, match='incomplete'):
            _identity_digest(get_snapshot_settings())
