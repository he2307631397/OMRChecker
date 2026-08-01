"""Service helpers for running OMRChecker from web/API code.

The existing CLI remains the source of truth. This module wraps it with a small,
framework-independent API that can be called by Robyn or tests.
"""

from __future__ import annotations

import csv
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.entry import entry_point

DEFAULT_TEMPLATE_DIR = Path("inputs")
DEFAULT_SERVICE_DATA_DIR = Path("service_data")


@dataclass(frozen=True)
class OmrRunResult:
    """Structured result returned by a service-mode OMR run."""

    input_dir: Path
    output_dir: Path
    results_csv: Path | None
    rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir),
            "results_csv": str(self.results_csv) if self.results_csv else None,
            "count": len(self.rows),
            "results": self.rows,
        }


def create_task_id() -> str:
    return uuid.uuid4().hex


def prepare_upload_input_dir(
    file_name: str,
    file_content: bytes,
    *,
    task_id: str | None = None,
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
    service_data_dir: Path = DEFAULT_SERVICE_DATA_DIR,
) -> tuple[str, Path, Path]:
    """Create an isolated task input/output directory for an uploaded OMR file.

    The task input directory receives the uploaded file plus the template/config
    copied from ``template_dir``. This keeps Web uploads compatible with the
    existing directory-oriented CLI pipeline.
    """

    task_id = task_id or create_task_id()
    task_root = service_data_dir / "tasks" / task_id
    input_dir = task_root / "input"
    output_dir = task_root / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=True)

    _copy_required_runtime_files(template_dir, input_dir)
    safe_file_name = Path(file_name).name or "upload.pdf"
    (input_dir / safe_file_name).write_bytes(file_content)
    return task_id, input_dir, output_dir


def run_omr_directory(
    input_dir: Path | str,
    output_dir: Path | str,
    *,
    auto_align: bool = False,
    debug: bool = False,
) -> OmrRunResult:
    """Run OMRChecker for a directory and return parsed CSV results."""

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    args = {
        "input_paths": [str(input_dir)],
        "output_dir": str(output_dir),
        # main.py uses action=store_false for --debug, so True suppresses tracebacks.
        # Service mode keeps tracebacks unless the caller explicitly asks otherwise.
        "debug": not debug,
        "autoAlign": auto_align,
        "setLayout": False,
    }
    entry_point(input_dir, args)
    results_csv = find_latest_results_csv(output_dir)
    rows = read_results_csv(results_csv) if results_csv else []
    return OmrRunResult(input_dir=input_dir, output_dir=output_dir, results_csv=results_csv, rows=rows)


def read_results_csv(results_csv: Path) -> list[dict[str, Any]]:
    """Read OMRChecker Results CSV into Java-friendly JSON rows."""

    with results_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    return [_normalize_result_row(row) for row in rows]


def find_latest_results_csv(output_dir: Path | str) -> Path | None:
    output_dir = Path(output_dir)
    result_files = sorted(output_dir.glob("**/Results/Results_*.csv"))
    if not result_files:
        return None
    return max(result_files, key=lambda path: path.stat().st_mtime)


def get_checked_image_path(output_dir: Path | str, file_id: str) -> Path | None:
    """Resolve a checked OMR image within an output directory."""

    safe_file_id = Path(file_id).name
    candidates = list(Path(output_dir).glob(f"**/CheckedOMRs/{safe_file_id}"))
    if not candidates:
        return None
    return candidates[0]


def _copy_required_runtime_files(template_dir: Path, input_dir: Path) -> None:
    for file_name in ("config.json", "template.json", "evaluation.json"):
        source = template_dir / file_name
        if source.exists():
            shutil.copy2(source, input_dir / file_name)


def _normalize_result_row(row: dict[str, str]) -> dict[str, Any]:
    id_keys = sorted(
        (key for key in row if re.fullmatch(r"id\d+", key)),
        key=lambda key: int(key[2:]),
    )
    id_digits = [row[key] for key in id_keys]
    answers = {key: value for key, value in row.items() if re.fullmatch(r"q\d+", key)}
    review_required = any(value == "" for value in answers.values())

    return {
        "file_id": row.get("file_id", ""),
        "input_path": row.get("input_path", ""),
        "output_path": row.get("output_path", ""),
        "score": row.get("score", ""),
        "exam_id": "".join(id_digits),
        "answers": answers,
        # Weak-mark details are currently emitted to logs by the core detector.
        # The field is reserved so the Java contract is stable when structured
        # weak-mark events are added.
        "weak_marks": [],
        "review_required": review_required,
    }
