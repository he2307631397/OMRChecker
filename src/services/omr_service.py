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

from src.constants.common import FIELD_TYPES
from src.entry import entry_point
from src.defaults import CONFIG_DEFAULTS
from src.evaluation import EvaluationConfig
from src.template import Template
from src.utils.parsing import open_config_with_defaults, open_template_with_defaults, parse_fields

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
    template_dir: Path | str | None = None,
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
    if template_dir is None:
        entry_point(input_dir, args)
    else:
        _run_omr_directory_with_template_dir(input_dir, output_dir, Path(template_dir), args)
    results_csv = find_latest_results_csv(output_dir)
    result_template_dir = Path(template_dir) if template_dir is not None else input_dir
    rows = read_results_csv(results_csv, template_dir=result_template_dir) if results_csv else []
    return OmrRunResult(input_dir=input_dir, output_dir=output_dir, results_csv=results_csv, rows=rows)


def _run_omr_directory_with_template_dir(
    input_dir: Path,
    output_dir: Path,
    template_dir: Path,
    args: dict[str, Any],
) -> None:
    from src.entry import process_dir
    from src.constants.common import CONFIG_FILENAME, EVALUATION_FILENAME, TEMPLATE_FILENAME

    tuning_config = CONFIG_DEFAULTS
    config_path = template_dir / CONFIG_FILENAME
    if config_path.exists():
        tuning_config = open_config_with_defaults(config_path)

    template = None
    template_path = template_dir / TEMPLATE_FILENAME
    if template_path.exists():
        template = Template(template_path, tuning_config)

    evaluation_config = None
    evaluation_path = template_dir / EVALUATION_FILENAME
    if not args["setLayout"] and evaluation_path.exists() and template is not None:
        evaluation_config = EvaluationConfig(template_dir, evaluation_path, template, tuning_config)

    process_dir(
        input_dir,
        input_dir,
        args,
        template=template,
        tuning_config=tuning_config,
        evaluation_config=evaluation_config,
    )


def read_results_csv(results_csv: Path, *, template_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Read OMRChecker Results CSV into Java-friendly JSON rows."""

    with results_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    field_regions = _load_field_region_metadata(Path(template_dir)) if template_dir is not None else {}
    review_confidences = _load_review_confidences(results_csv)
    ocr_results = _load_ocr_results(results_csv)
    return [
        _normalize_result_row(
            row,
            field_regions=field_regions,
            review_confidences=review_confidences.get(row.get("file_id", ""), {}),
            ocr_results=ocr_results.get(row.get("file_id", ""), {}),
        )
        for row in rows
    ]


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


def _normalize_result_row(
    row: dict[str, str],
    *,
    field_regions: dict[str, dict[str, Any]] | None = None,
    review_confidences: dict[str, float] | None = None,
    ocr_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    id_keys = sorted(
        (key for key in row if re.fullmatch(r"id\d+", key)),
        key=lambda key: int(key[2:]),
    )
    id_digits = [row[key] for key in id_keys]
    ocr_results = ocr_results or {}
    ocr_fields = {
        key
        for key, metadata in (field_regions or {}).items()
        if metadata.get("engine") == "paddleocr" and key in row
    } | {field for field in ocr_results if field in row}
    flat_answers = {
        key: value
        for key, value in row.items()
        if re.fullmatch(r"q\d+", key) or key in ocr_fields
    }
    recognized_fields = {
        **{key: row[key] for key in id_keys},
        **flat_answers,
    }
    answers = _group_answers_by_region_type(
        recognized_fields,
        field_regions=field_regions or {},
        review_confidences=review_confidences or {},
        ocr_results=ocr_results,
    )
    review_required = any(value == "" for value in recognized_fields.values())

    return {
        "file_id": row.get("file_id", ""),
        "input_path": row.get("input_path", ""),
        "output_path": row.get("output_path", ""),
        "score": row.get("score", ""),
        "exam_id": "".join(id_digits),
        "answers": answers,
        "answers_flat": flat_answers,
        # Weak-mark details are currently emitted to logs by the core detector.
        # The field is reserved so the Java contract is stable when structured
        # weak-mark events are added.
        "weak_marks": [],
        "review_required": review_required,
    }


def _group_answers_by_region_type(
    flat_answers: dict[str, str],
    *,
    field_regions: dict[str, dict[str, Any]],
    review_confidences: dict[str, float],
    ocr_results: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    ocr_results = ocr_results or {}
    for field, value in flat_answers.items():
        metadata = field_regions.get(field, {})
        ocr_metadata = ocr_results.get(field, {})
        fallback_region = _infer_business_region(field)
        region_code = (
            ocr_metadata.get("regionCode")
            or metadata.get("regionCode")
            or fallback_region["regionCode"]
        )
        region = grouped.setdefault(
            region_code,
            {
                "regionCode": region_code,
                "regionName": ocr_metadata.get("regionName")
                or metadata.get("regionName")
                or fallback_region["regionName"],
                "type": ocr_metadata.get("type") or metadata.get("type") or fallback_region["type"],
                "items": [],
            },
        )
        engine = ocr_metadata.get("engine") or metadata.get("engine")
        if engine == "paddleocr":
            region["engine"] = engine
        confidence = ocr_metadata.get("confidence")
        if confidence is None:
            confidence = review_confidences.get(field)
        if confidence is None:
            confidence = 1.0 if value != "" else 0.0
        item = {
            "field": field,
            "value": value,
            "confidence": round(float(confidence), 3),
        }
        artifact_local_path = ocr_metadata.get("artifactLocalPath")
        if artifact_local_path:
            item["artifactLocalPath"] = artifact_local_path
        region["items"].append(item)
    return list(grouped.values())


def _infer_business_region(field: str) -> dict[str, str]:
    if re.fullmatch(r"q\d+", field):
        return {"regionCode": "singleChoice", "regionName": "单选题区域", "type": "SINGLE_CHOICE"}
    if re.fullmatch(r"id\d+", field):
        return {"regionCode": "candidateNumber", "regionName": "准考证号区域", "type": "DIGIT"}
    return {"regionCode": "other", "regionName": "其他识别区域", "type": "OTHER"}


def _load_field_region_metadata(template_dir: Path) -> dict[str, dict[str, Any]]:
    template_path = template_dir / "template.json"
    if not template_path.exists():
        return {}
    try:
        template = open_template_with_defaults(template_path)
    except Exception:
        return {}

    metadata: dict[str, dict[str, Any]] = {}
    for region_code, field_block in (template.get("fieldBlocks") or {}).items():
        field_type = field_block.get("fieldType") or "__CUSTOM__"
        merged = {**FIELD_TYPES.get(field_type, {}), **field_block}
        try:
            labels = parse_fields(f"Field Block Labels: {region_code}", merged.get("fieldLabels") or [])
        except Exception:
            labels = []
        default_region = _default_business_region_for_field_block(field_type, merged)
        engine = merged.get("engine") or "omr"
        for label in labels:
            metadata[label] = {
                "regionCode": merged.get("regionCode") or default_region["regionCode"],
                "regionName": merged.get("name") or merged.get("regionName") or default_region["regionName"],
                "type": merged.get("type") or default_region["type"],
                "engine": engine,
            }
    return metadata


def _default_business_region_for_field_block(field_type: str, field_block: dict[str, Any]) -> dict[str, str]:
    if field_type.startswith("QTYPE_MCQ"):
        if field_block.get("multiSelect"):
            return {"regionCode": "multipleChoice", "regionName": "多选题区域", "type": "MULTIPLE_CHOICE"}
        return {"regionCode": "singleChoice", "regionName": "单选题区域", "type": "SINGLE_CHOICE"}
    if field_type.startswith("QTYPE_INT"):
        return {"regionCode": "candidateNumber", "regionName": "准考证号区域", "type": "DIGIT"}
    return {"regionCode": "other", "regionName": "其他识别区域", "type": "OTHER"}


def _load_review_confidences(results_csv: Path) -> dict[str, dict[str, float]]:
    review_csv = results_csv.parent / "WeakFillReview.csv"
    if not review_csv.exists():
        return {}
    confidences: dict[str, dict[str, float]] = {}
    try:
        with review_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                file_id = row.get("file_id", "")
                field = row.get("field", "")
                if not file_id or not field:
                    continue
                try:
                    confidence = float(row.get("confidence", ""))
                except ValueError:
                    continue
                confidences.setdefault(file_id, {})[field] = confidence
    except Exception:
        return {}
    return confidences


def _load_ocr_results(results_csv: Path) -> dict[str, dict[str, dict[str, Any]]]:
    ocr_csv = results_csv.parent / "OcrResults.csv"
    if not ocr_csv.exists():
        return {}
    results: dict[str, dict[str, dict[str, Any]]] = {}
    try:
        with ocr_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                file_id = row.get("file_id", "")
                field = row.get("field", "")
                if not file_id or not field:
                    continue
                metadata: dict[str, Any] = {
                    "value": row.get("value", ""),
                    "engine": row.get("engine", ""),
                    "regionCode": row.get("regionCode", ""),
                    "regionName": row.get("regionName", ""),
                    "type": row.get("type", ""),
                    "artifactLocalPath": row.get("artifactLocalPath", ""),
                }
                try:
                    metadata["confidence"] = float(row.get("confidence", ""))
                except ValueError:
                    pass
                results.setdefault(file_id, {})[field] = metadata
    except Exception:
        return {}
    return results
