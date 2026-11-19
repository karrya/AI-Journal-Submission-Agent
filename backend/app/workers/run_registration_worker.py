import os
import signal
import socket
from threading import Event

from app.core.config import get_settings
from app.core.database import create_mysql_engine
from app.workers.registration_worker import RegistrationWorker


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def main() -> None:
    settings = get_settings()
    engine = create_mysql_engine(settings.database_url)
    stop = Event()

    def request_stop(signum, frame) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    worker = RegistrationWorker(
        engine,
        worker_id=os.environ.get("REGISTRATION_WORKER_ID", default_worker_id()),
    )
    try:
        worker.run_forever(
            poll_interval=float(
                os.environ.get(
                    "REGISTRATION_POLL_INTERVAL", settings.discovery_poll_interval
                )
            ),
            stop_event=stop,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
