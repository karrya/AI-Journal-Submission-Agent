import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from app.core.test_guards import validate_test_environment
from conftest import validate_test_database_url


TEST_DATABASE = "academic_submission_agent_test"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_test_guard_requires_explicit_environment_and_host():
    with pytest.raises(TypeError):
        validate_test_environment(TEST_DATABASE, "/tmp/test", "storage")


def test_test_storage_cannot_equal_live_storage():
    with pytest.raises(RuntimeError, match="live storage"):
        validate_test_environment(
            TEST_DATABASE,
            "storage",
            "storage",
            environment="test",
            database_host="127.0.0.1",
        )


def test_test_storage_cannot_be_nested_in_live_storage(tmp_path: Path):
    live_storage = tmp_path / "storage"
    with pytest.raises(RuntimeError, match="live storage"):
        validate_test_environment(
            TEST_DATABASE,
            live_storage / "pytest",
            live_storage,
            environment="test",
            database_host="127.0.0.1",
        )


def test_non_test_database_is_rejected():
    with pytest.raises(RuntimeError, match="_test"):
        validate_test_environment(
            "academic_submission_agent",
            "/tmp/test",
            "storage",
            environment="test",
            database_host="127.0.0.1",
        )


def test_non_loopback_database_host_is_rejected():
    with pytest.raises(RuntimeError, match="loopback"):
        validate_test_environment(
            TEST_DATABASE,
            "/tmp/test",
            "storage",
            environment="test",
            database_host="192.0.2.1",
        )


def test_non_test_environment_is_rejected():
    with pytest.raises(RuntimeError, match="ENVIRONMENT=test"):
        validate_test_environment(
            TEST_DATABASE,
            "/tmp/test",
            "storage",
            environment="development",
            database_host="127.0.0.1",
        )


def test_pytest_database_url_guard_rejects_remote_host():
    with pytest.raises(RuntimeError, match="loopback"):
        validate_test_database_url(
            "mysql+pymysql://test@192.0.2.1/academic_submission_agent_test"
        )


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1"])
def test_isolated_test_environment_is_accepted(tmp_path: Path, host: str):
    validate_test_environment(
        TEST_DATABASE,
        tmp_path / "test-storage",
        tmp_path / "live-storage",
        environment="test",
        database_host=host,
    )


def write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def copy_project_script(name: str, project_root: Path) -> Path:
    source = PROJECT_ROOT / "scripts" / name
    assert source.is_file(), f"scripts/{name} is required"
    target = project_root / "scripts" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def test_api_runner_rejects_live_storage_before_migration_or_newman():
    environment = os.environ.copy()
    environment["TEST_DATABASE_URL"] = (
        "mysql+pymysql://guard:guard@127.0.0.1:1/"
        "academic_submission_agent_test"
    )
    environment["TEST_STORAGE_ROOT"] = str(PROJECT_ROOT / "storage")

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "test_api.sh")],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "live storage" in output
    assert "alembic.runtime.migration" not in output
    assert "newman" not in output.lower()


def test_dev_backend_runs_uvicorn_on_loopback(tmp_path: Path):
    script = copy_project_script("dev_backend.sh", tmp_path)
    capture = tmp_path / "backend-arguments"
    write_executable(
        tmp_path / ".venv" / "bin" / "python",
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n',
    )
    environment = os.environ.copy()
    environment["CAPTURE_FILE"] = str(capture)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "backend",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]


def test_dev_frontend_runs_vite_on_loopback(tmp_path: Path):
    script = copy_project_script("dev_frontend.sh", tmp_path)
    capture = tmp_path / "frontend-arguments"
    write_executable(
        tmp_path / "bin" / "npm",
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n',
    )
    environment = os.environ.copy()
    environment["CAPTURE_FILE"] = str(capture)
    environment["PATH"] = str(tmp_path / "bin") + os.pathsep + environment["PATH"]

    result = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "--prefix",
        "frontend",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
    ]


def test_verify_stops_on_first_failure_with_the_command_visible(tmp_path: Path):
    (tmp_path / "backend").mkdir()
    script = copy_project_script("verify.sh", tmp_path)
    write_executable(tmp_path / ".venv" / "bin" / "python", "#!/bin/sh\nexit 0\n")
    write_executable(tmp_path / ".venv" / "bin" / "ruff", "#!/bin/sh\nexit 23\n")
    write_executable(
        tmp_path / ".venv" / "bin" / "mypy",
        '#!/bin/sh\nprintf "should not run" > "$CAPTURE_FILE"\n',
    )
    capture = tmp_path / "mypy-ran"
    environment = os.environ.copy()
    environment["CAPTURE_FILE"] = str(capture)

    result = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 23
    assert "ruff check app tests" in output
    assert "Verification failed" in output
    assert not capture.exists()
