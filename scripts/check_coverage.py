#!/usr/bin/env python3
"""强制执行后端整体及各分层的语句覆盖率下限。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "backend" / "coverage.json"
LAYER_FLOORS = (
    ("permissions", ("app/services/permissions",), 95.0),
    ("files", ("app/services/files",), 90.0),
    ("file_validation", ("app/services/file_validation",), 90.0),
    ("storage", ("app/services/storage",), 90.0),
    ("services", ("app/services/",), 85.0),
    ("api", ("app/api/",), 80.0),
)


def _percentage(files: list[dict[str, Any]], label: str) -> float:
    covered = sum(item["summary"]["covered_lines"] for item in files)
    statements = sum(item["summary"]["num_statements"] for item in files)
    if statements == 0:
        raise ValueError(f"覆盖率报告中 {label} 没有可统计语句")
    return covered * 100.0 / statements


def evaluate_report(report: dict[str, Any]) -> dict[str, float]:
    percentages = {"backend": float(report["totals"]["percent_covered"])}
    if percentages["backend"] < 80.0:
        raise ValueError(f"backend 整体覆盖率 {percentages['backend']:.2f}% < 80.00%")

    for label, prefixes, floor in LAYER_FLOORS:
        files = [
            summary
            for path, summary in report["files"].items()
            if any(path.startswith(prefix) for prefix in prefixes)
        ]
        percentage = _percentage(files, label)
        percentages[label] = percentage
        if percentage < floor:
            raise ValueError(f"{label} 覆盖率 {percentage:.2f}% < {floor:.2f}%")
    return percentages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=DEFAULT_REPORT)
    arguments = parser.parse_args()
    with arguments.report.open(encoding="utf-8") as source:
        report = json.load(source)
    percentages = evaluate_report(report)
    floors = {"backend": 80.0, **{label: floor for label, _, floor in LAYER_FLOORS}}
    for label, percentage in percentages.items():
        print(f"{label}：{percentage:.2f}%（下限 {floors[label]:.2f}%）")


if __name__ == "__main__":
    main()
