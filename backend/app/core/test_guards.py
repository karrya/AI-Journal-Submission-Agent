from pathlib import Path


LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_test_environment(
    database_name: str | None,
    test_storage_root: str | Path,
    live_storage_root: str | Path,
    *,
    environment: str | None = "test",
    database_host: str | None = "127.0.0.1",
) -> None:
    """Reject unsafe configuration before tests migrate or delete data."""
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError("tests require a database name ending in _test")
    if database_host not in LOOPBACK_HOSTS:
        raise RuntimeError("tests require an explicit loopback database host")
    if environment != "test":
        raise RuntimeError("tests require ENVIRONMENT=test")

    test_storage = Path(test_storage_root).resolve()
    live_storage = Path(live_storage_root).resolve()
    if test_storage == live_storage or live_storage in test_storage.parents:
        raise RuntimeError("tests cannot use the live storage directory")
