import os
import subprocess
from pathlib import Path


def test_api_runner_rejects_remote_database_before_migration_or_newman():
    project_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["TEST_DATABASE_URL"] = (
        "mysql+pymysql://contract:contract@192.0.2.1:1/"
        "academic_submission_agent_test"
    )

    result = subprocess.run(
        ["bash", str(project_root / "scripts" / "test_api.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "explicit loopback" in output
    assert "alembic.runtime.migration" not in output
    assert "newman" not in output.lower()
