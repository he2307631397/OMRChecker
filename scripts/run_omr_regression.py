#!/usr/bin/env python3
"""Run local OMRChecker four-scenario regression and write recognition reports.

Generated runtime directories are intentionally kept outside git-tracked assets:

- .jcode_runs/regression/<scenario>
- outputs/<scenario>
- jcode_regression_<scenario>.log
- outputs/recognition_rate_report.{csv,md}
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
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
TEMPLATE_SOURCE = Path("inputs")
REPORT_COLUMNS = [
    "scenario",
    "asset_dir",
    "pdf_count",
    "rows",
    "id_total_cells",
    "id_blank_cells",
    "id_recognized_cells",
    "id_recognition_rate",
    "q_total_cells",
    "q_blank_cells",
    "q_recognized_cells",
    "q_recognition_rate",
    "total_cells",
    "blank_cells",
    "recognized_cells",
    "overall_recognition_rate",
    "blank_rows",
    "csv",
]


def prepare_run_dir(root: Path, scenario: str, asset_dir: str) -> Path:
    """Create an isolated input directory for one scenario."""

    run_dir = root / scenario
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    for name in RUNTIME_FILES:
        source = TEMPLATE_SOURCE / name
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

    id_total_cells = len(rows) * len(id_cols)
    q_total_cells = len(rows) * len(q_cols)
    id_blank_cells = sum(col.startswith("id") for _, col in blanks)
    q_blank_cells = sum(col.startswith("q") for _, col in blanks)
    total_cells = id_total_cells + q_total_cells
    blank_cells = len(blanks)

    return {
        "rows": len(rows),
        "id_columns": len(id_cols),
        "q_columns": len(q_cols),
        "id_total_cells": id_total_cells,
        "q_total_cells": q_total_cells,
        "total_cells": total_cells,
        "id_blank_cells": id_blank_cells,
        "q_blank_cells": q_blank_cells,
        "blank_cells": blank_cells,
        "id_recognized_cells": id_total_cells - id_blank_cells,
        "q_recognized_cells": q_total_cells - q_blank_cells,
        "recognized_cells": total_cells - blank_cells,
        "id_recognition_rate": _rate(id_total_cells - id_blank_cells, id_total_cells),
        "q_recognition_rate": _rate(q_total_cells - q_blank_cells, q_total_cells),
        "overall_recognition_rate": _rate(total_cells - blank_cells, total_cells),
        "blank_rows": len({file_id for file_id, _ in blanks}),
        "csv": str(result_csv),
        "blanks": blanks,
    }


def summarize_log(log_path: Path) -> dict[str, int]:
    """Count fallback and review events emitted in one run log."""

    text = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""
    return {pattern: len(re.findall(re.escape(pattern), text)) for pattern in FALLBACK_PATTERNS}


def run_scenario(scenario: str, run_dir: Path) -> tuple[dict, dict[str, int]]:
    output_dir = Path("outputs") / scenario
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


def write_reports(rows: list[tuple[str, dict, dict[str, int]]]) -> None:
    outputs = Path("outputs")
    outputs.mkdir(exist_ok=True)
    csv_path = outputs / "recognition_rate_report.csv"
    md_path = outputs / "recognition_rate_report.md"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        for scenario, summary, _fallbacks in rows:
            row = {column: summary.get(column, "") for column in REPORT_COLUMNS}
            row["scenario"] = scenario
            row["asset_dir"] = SCENARIOS[scenario]
            row["pdf_count"] = len(list((Path("docs/assets") / SCENARIOS[scenario]).glob("*.pdf")))
            writer.writerow(row)

    lines = [
        "# 本地答题卡四场景识别率测试报告",
        "",
        f"- 生成时间 UTC: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}`",
        "- 运行方式: 本地命令行 `python main.py`，非 web 服务方式",
        "- 输出目录: `outputs/`",
        "- 统计口径: 识别率 = 非空单元格数 / 应识别单元格数。ID 与题目分别统计，并给出总体识别率。",
        "",
        "## 汇总",
        "",
        "| 场景 | PDF 数 | rows | ID识别率 | 题目识别率 | 总体识别率 | ID空白 | 题目空白 | 总空白 | 空白行 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario, summary, _fallbacks in rows:
        lines.append(
            "| {scenario} | {pdf_count} | {rows} | {id_rate:.2%} | {q_rate:.2%} | "
            "{overall_rate:.2%} | {id_blank_cells} | {q_blank_cells} | {blank_cells} | {blank_rows} |".format(
                scenario=f"{scenario} ({SCENARIOS[scenario]})",
                pdf_count=len(list((Path("docs/assets") / SCENARIOS[scenario]).glob("*.pdf"))),
                rows=summary["rows"],
                id_rate=summary["id_recognition_rate"],
                q_rate=summary["q_recognition_rate"],
                overall_rate=summary["overall_recognition_rate"],
                id_blank_cells=summary["id_blank_cells"],
                q_blank_cells=summary["q_blank_cells"],
                blank_cells=summary["blank_cells"],
                blank_rows=summary["blank_rows"],
            )
        )
    lines.extend(["", "## 明细", ""])
    for scenario, summary, fallbacks in rows:
        lines.extend(
            [
                f"### {scenario} ({SCENARIOS[scenario]})",
                "",
                f"- 结果 CSV: `{summary['csv']}`",
                f"- ID: {summary['id_recognized_cells']}/{summary['id_total_cells']} = {summary['id_recognition_rate']:.2%}",
                f"- 题目: {summary['q_recognized_cells']}/{summary['q_total_cells']} = {summary['q_recognition_rate']:.2%}",
                f"- 总体: {summary['recognized_cells']}/{summary['total_cells']} = {summary['overall_recognition_rate']:.2%}",
                f"- fallback/review 事件: `{fallbacks}`",
            ]
        )
        blanks = summary.get("blanks", [])
        if blanks:
            lines.append("- 空白单元格:")
            for file_id, col in blanks:
                lines.append(f"  - `{file_id}` `{col}`")
        else:
            lines.append("- 空白单元格: 无")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


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
    write_reports(rows)
    print_summary(rows)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _natural_suffix(value: str) -> int:
    match = re.search(r"\d+$", value)
    return int(match.group(0)) if match else 0


if __name__ == "__main__":
    main()
