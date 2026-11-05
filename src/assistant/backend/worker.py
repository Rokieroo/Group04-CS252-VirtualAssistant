"""Background worker: ``python -m assistant.backend.worker`` (Compose service ``worker``).

Run as many as needed against one database; claims and the daily dedupe keep them
from doing the same work twice. The API applies migrations, so start it first.
"""

import logging
import signal
import threading

# Importing these modules registers their job handlers.
from . import maintenance, material_repository, resources  # noqa: F401
from .config import Settings
from .database import Database
from .jobs import run_once
from .models import utcnow

log = logging.getLogger(__name__)
POLL_SECONDS = 2.0
ERROR_PAUSE_SECONDS = 10.0


def serve(database: Database, stop: threading.Event) -> None:
    """Run due jobs until ``stop`` is set; sleep only when the queue is empty."""
    scheduled_for = None
    while not stop.is_set():
        try:
            now = utcnow()
            if scheduled_for != now.date():
                with database.sessions() as db:
                    maintenance.schedule_daily(db, now)
                    db.commit()
                scheduled_for = now.date()
            if run_once(database.sessions, now) is None:
                stop.wait(POLL_SECONDS)
        except Exception:  # e.g. the database restarted; keep the worker alive
            log.exception("worker loop failed; retrying")
            stop.wait(ERROR_PAUSE_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    database = Database(Settings.from_env().database_url)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        # Finish the current job, then exit.
        signal.signal(signum, lambda *_: stop.set())
    log.info("worker started")
    serve(database, stop)
    database.engine.dispose()


if __name__ == "__main__":
    main()
