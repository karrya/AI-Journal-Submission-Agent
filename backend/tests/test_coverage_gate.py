import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_gate():
    spec = importlib.util.spec_from_file_location(
        "check_coverage", PROJECT_ROOT / "scripts" / "check_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def file_summary(covered: int, statements: int = 100) -> dict:
    return {"summary": {"covered_lines": covered, "num_statements": statements}}


def passing_report() -> dict:
    return {
        "totals": {"percent_covered": 95.5},
        "files": {
            "app/api/v1/authors.py": file_summary(80),
            "app/services/permissions.py": file_summary(95),
            "app/services/files.py": file_summary(90),
            "app/services/file_validation.py": file_summary(90),
            "app/services/storage.py": file_summary(90),
            "app/services/authors.py": file_summary(85),
        },
    }


def test_coverage_gate_reports_overall_and_every_layer_percentage():
    result = load_gate().evaluate_report(passing_report())
    assert result == {
        "backend": 95.5,
        "permissions": 95.0,
        "files": 90.0,
        "file_validation": 90.0,
        "storage": 90.0,
        "services": 90.0,
        "api": 80.0,
    }


@pytest.mark.parametrize(
    ("path", "covered", "label"),
    [
        ("app/services/permissions.py", 94, "permissions"),
        ("app/services/files.py", 89, "files"),
        ("app/services/file_validation.py", 89, "file_validation"),
        ("app/services/storage.py", 89, "storage"),
        ("app/api/v1/authors.py", 79, "api"),
    ],
)
def test_coverage_gate_rejects_each_layer_below_its_floor(path, covered, label):
    report = passing_report()
    report["files"][path] = file_summary(covered)
    with pytest.raises(ValueError, match=label):
        load_gate().evaluate_report(report)


def test_coverage_gate_rejects_low_aggregate_services():
    report = passing_report()
    report["files"]["app/services/large_uncovered.py"] = file_summary(0, 1000)
    with pytest.raises(ValueError, match="services"):
        load_gate().evaluate_report(report)


def test_coverage_gate_rejects_low_overall_and_empty_layers():
    gate = load_gate()
    report = passing_report()
    report["totals"]["percent_covered"] = 79.99
    with pytest.raises(ValueError, match="backend"):
        gate.evaluate_report(report)
    report = passing_report()
    del report["files"]["app/services/permissions.py"]
    with pytest.raises(ValueError, match="permissions has no statements"):
        gate.evaluate_report(report)
