import logging
import os
import signal
import sys
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SQLiteSnapshotsConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "pm_sqlite_snapshots"
    verbose_name = "SQLite snapshots"

    def ready(self):
        from .runtime import install_signal_handlers, maybe_restore_on_startup, start_scheduler
        from .settings import get_snapshot_settings

        config = get_snapshot_settings()
        if not config.enabled:
            return
        if os.environ.get("RUN_MAIN") == "true":
            return
        if _is_management_command_without_runtime_hooks():
            return

        try:
            maybe_restore_on_startup(config)
            start_scheduler(config)
            install_signal_handlers(config)
        except Exception:
            logger.exception("Failed to initialize SQLite snapshot runtime")
            if config.fail_startup_if_restore_missing:
                raise


def _is_management_command_without_runtime_hooks():
    if len(sys.argv) < 2:
        return False
    executable = Path(sys.argv[0]).name
    runtime_commands = {
        "daphne",
        "gunicorn",
        "uvicorn",
    }
    if executable in runtime_commands:
        return False
    if sys.argv[0].endswith("manage.py") and sys.argv[1] != "runserver":
        return True
    command = sys.argv[1]
    allowed = {
        "runserver",
        "daphne",
        "uvicorn",
        "gunicorn",
    }
    return command not in allowed
