#!/usr/bin/env python3
"""Run OMRChecker four-scenario regression and print compact metrics.

Generated runtime directories are intentionally kept outside git-tracked assets:

- .jcode_runs/regression/<scenario>
- outputs_jcode_regression_<scenario>
- jcode_regression_<scenario>.log
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCENARIOS = {
    "weak": "淡涂答题卡归档",
    "normal": "正常填涂测试答题卡归档",
    "underfill": "没涂满答题卡归档",
    "overflow": "涂超出答题卡归档",
}

FALLBACK_PATTERNS = [
    "Weak identifier fallback",
    "Weak mark fallback",
    "Weak multi-mark fallback",
    "Weak multi full-select fallback",
    "Weak mark candidate review",
    "Single-choice conflict",
]

RUNTIME_FILES = ["config.json", "template.json", "reference.png"]


def prepare_run_dir(root: Path, scenario: str, asset_dir: str) -> Path:
    """Create an isolated input directory for one scenario."""

    run_dir = root / scenario
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    for name in RUNTIME_FILES:
        source = Path("inputs") / name
        if source.exists():
            shutil.copy2(source, run_dir / name)

    source_dir = Path("docs/assets") / asset_dir
    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found for scenario '{scenario}' in {source_dir}")
    for pdf in pdfs:
        shutil.copy2(pdf, run_dir / pdf.name)
    return run_dir


def summarize_csv(output_dir: Path) -> dict:
    """Summarize blank cells from the latest OMRChecker Results CSV."""

    csvs = sorted((output_dir / "Results").glob("Results_*.csv"))
    if not csvs:
        return {
            "rows": 0,
            "id_blank_cells": 0,
            "q_blank_cells": 0,
            "blank_cells": 0,
            "blank_rows": 0,
            "csv": "",
            "blanks": [],
        }

    result_csv = csvs[-1]
    with result_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    columns = rows[0].keys() if rows else []
    id_cols = sorted((col for col in columns if re.fullmatch(r"id\d+", col)), key=_natural_suffix)
    q_cols = sorted((col for col in columns if re.fullmatch(r"q\d+", col)), key=_natural_suffix)

    blanks: list[tuple[str, str]] = []
    for row in rows:
        file_id = row.get("file_id") or next(iter(row.values()), "")
        for col in [*id_cols, *q_cols]:
            if not (row.get(col, "") or "").strip():
                blanks.append((file_id, col))

    return {
        "rows": len(rows),
        "id_blank_cells": sum(col.startswith("id") for _, col in blanks),
        "q_blank_cells": sum(col.startswith("q") for _, col in blanks),
        "blank_cells": len(blanks),
        "blank_rows": len({file_id for file_id, _ in blanks}),
        "csv": str(result_csv),
        "blanks": blanks,
    }


def summarize_log(log_path: Path) -> dict[str, int]:
    """Count fallback and review events emitted in one run log."""

    text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
    return {pattern: len(re.findall(re.escape(pattern), text)) for pattern in FALLBACK_PATTERNS}


def run_scenario(scenario: str, run_dir: Path) -> tuple[dict, dict[str, int]]:
    output_dir = Path(f"outputs_jcode_regression_{scenario}")
    log_path = Path(f"jcode_regression_{scenario}.log")
    if output_dir.exists():
        shutil.rmtree(output_dir)

    with log_path.open("w", encoding="utf-8") as log_file:
        completed = subprocess.run(
            [sys.executable, "main.py", "-i", str(run_dir), "-o", str(output_dir)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        raise SystemExit(f"{scenario} failed with exit {completed.returncode}; see {log_path}")
    return summarize_csv(output_dir), summarize_log(log_path)


def print_summary(rows: list[tuple[str, dict, dict[str, int]]]) -> None:
    for scenario, summary, fallbacks in rows:
        print(f"SCENARIO {scenario}")
        print(
            " rows={rows} id_blank_cells={id_blank_cells} q_blank_cells={q_blank_cells} "
            "blank_cells={blank_cells} blank_rows={blank_rows}".format(**summary)
        )
        print(f" csv={summary['csv']}")
        print(f" fallbacks={fallbacks}")
        for file_id, col in summary.get("blanks", [])[:40]:
            print(f" blank {file_id} {col}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        action="append",
        help="Run only one scenario. Can be passed multiple times.",
    )
    parser.add_argument(
        "--run-root",
        default=".jcode_runs/regression",
        help="Directory for generated per-scenario input copies.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested = args.scenario or list(SCENARIOS)
    run_root = Path(args.run_root)
    rows = []
    for scenario in requested:
        run_dir = prepare_run_dir(run_root, scenario, SCENARIOS[scenario])
        summary, fallbacks = run_scenario(scenario, run_dir)
        rows.append((scenario, summary, fallbacks))
    print_summary(rows)


def _natural_suffix(value: str) -> int:
    match = re.search(r"\d+$", value)
    return int(match.group(0)) if match else 0


if __name__ == "__main__":
    main()
