import os
import signal
import socket
from threading import Event

from app.automation.registration_adapters import LabelFormRegistrationAdapter
from app.automation.registration_data import RegistrationDataProvider
from app.automation.registration_executor import RegistrationAutomationExecutor
from app.automation.registration_preflight import RegistrationAdapterRegistry, RegistrationPreflight
from app.core.config import get_settings
from app.core.database import create_mysql_engine
from app.crawlers.url_security import SafeHttpClient
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
    registry = RegistrationAdapterRegistry()
    registry.register("LABEL_FORM", "1.0.0", LabelFormRegistrationAdapter())
    automation_executor = RegistrationAutomationExecutor(
        preflight=RegistrationPreflight(
            adapters=registry,
            url_checker=SafeHttpClient(),
        ),
        provider=RegistrationDataProvider(),
        adapters=registry,
    )
    worker = RegistrationWorker(
        engine,
        worker_id=os.environ.get("REGISTRATION_WORKER_ID", default_worker_id()),
    )
    worker.executor = lambda task, session: automation_executor.execute(
        task, session, worker.save_checkpoint
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
