import logging
import os
import signal
import threading

from .core import SnapshotError, export_snapshot, get_sqlite_database_path, restore_snapshot

logger = logging.getLogger(__name__)

_scheduler_started = False
_shutdown_export_started = False


def maybe_restore_on_startup(config):
    if not config.restore_on_startup:
        return
    db_path = get_sqlite_database_path(config.database_alias)
    if os.path.exists(db_path) and not config.restore_if_db_missing:
        return
    if os.path.exists(db_path):
        return
    try:
        snapshot = restore_snapshot(config, force=True)
        logger.info("Restored SQLite snapshot %s on startup", snapshot.snapshot_id)
    except SnapshotError:
        if config.fail_startup_if_restore_missing:
            raise
        logger.warning("No SQLite snapshot restored on startup", exc_info=True)


def start_scheduler(config):
    global _scheduler_started
    if _scheduler_started or config.interval_seconds <= 0:
        return
    _scheduler_started = True
    thread = threading.Thread(target=_scheduler_loop, args=(config,), daemon=True)
    thread.start()


def install_signal_handlers(config):
    if not config.export_on_shutdown:
        return
    previous_term = signal.getsignal(signal.SIGTERM)
    previous_int = signal.getsignal(signal.SIGINT)

    def handle(signum, frame):
        export_on_shutdown(config)
        _delegate_signal(previous_term if signum == signal.SIGTERM else previous_int, signum, frame)

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)


def export_on_shutdown(config):
    global _shutdown_export_started
    if _shutdown_export_started:
        return
    _shutdown_export_started = True
    try:
        snapshot = export_snapshot(config, reason="shutdown")
        logger.info("Exported SQLite shutdown snapshot %s", snapshot.snapshot_id)
    except Exception:
        logger.exception("Failed to export SQLite snapshot during shutdown")


def _scheduler_loop(config):
    interval = max(1, int(config.interval_seconds))
    stop_event = threading.Event()
    while not stop_event.wait(interval):
        try:
            snapshot = export_snapshot(config, reason="periodic")
            logger.info("Exported periodic SQLite snapshot %s", snapshot.snapshot_id)
        except Exception:
            logger.exception("Failed to export periodic SQLite snapshot")


def _delegate_signal(previous_handler, signum, frame):
    if callable(previous_handler):
        previous_handler(signum, frame)
    elif previous_handler == signal.SIG_DFL:
        raise SystemExit(128 + signum)
