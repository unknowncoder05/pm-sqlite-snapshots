import os

SECRET_KEY = 'offline-bootstrap-test'
INSTALLED_APPS = ['django.contrib.contenttypes', 'pm_sqlite_snapshots']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ['BOOTSTRAP_TEST_DB'],
    },
}
SQLITE_SNAPSHOTS = {
    'ENABLED': True,
    'RESTORE_ON_STARTUP': True,
    'RESTORE_IF_DB_MISSING': True,
    'FAIL_STARTUP_IF_RESTORE_MISSING': True,
    'REQUIRE_IDENTITY_RECEIPT': True,
    'STORAGE': {
        'BACKEND': 'pm_sqlite_snapshots.storage.local.LocalSnapshotStorage',
        'PATH': os.environ['BOOTSTRAP_TEST_STORE'],
        'PREFIX': 'fixed-project/sqlite/',
    },
}
