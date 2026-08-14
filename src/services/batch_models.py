from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(frozen=True)
class BatchSheetRequest:
    sheet_id: str
    osskey: str
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_api_json(cls, payload: Any, *, index: int = 0) -> "BatchSheetRequest":
        if not isinstance(payload, dict):
            raise ValueError(f"sheets[{index}] must be an object")
        sheet_id = _required_non_empty_scalar(payload, "sheetId", f"sheets[{index}].sheetId")
        osskey = _required_non_empty_string(payload, "osskey", f"sheets[{index}].osskey")
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError(f"sheets[{index}].metadata must be an object")
        return cls(sheet_id=sheet_id, osskey=osskey, metadata=metadata)

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"sheetId": self.sheet_id, "osskey": self.osskey}
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True)
class BatchRecognitionRequest:
    exam_id: str
    callback_url: str | None
    sheets: list[BatchSheetRequest]
    external_batch_id: str | None = None
    template_code: str | None = None
    schema_version: str | None = None
    template_version: str | None = None
    recognition_config: dict[str, Any] = field(default_factory=dict)
    debug_artifacts: bool | None = None
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_json(cls, payload: Any) -> "BatchRecognitionRequest":
        if not isinstance(payload, dict):
            raise ValueError("request body must be an object")
        exam_id = _required_non_empty_scalar(payload, "examId", "examId")
        callback_url = _optional_non_empty_string(payload.get("callbackUrl"), "callbackUrl")
        external_batch_id = _optional_non_empty_string(payload.get("externalBatchId"), "externalBatchId")
        template_code = _optional_template_path_component(payload.get("templateCode"), "templateCode")
        schema_version = _optional_template_path_component(payload.get("schemaVersion"), "schemaVersion")
        template_version = _optional_template_version(payload.get("templateVersion"), "templateVersion")
        if schema_version is not None and template_code is None:
            raise ValueError("templateCode is required when schemaVersion is supplied")

        recognition_config = payload.get("recognitionConfig", {})
        if recognition_config is None:
            recognition_config = {}
        if not isinstance(recognition_config, dict):
            raise ValueError("recognitionConfig must be an object")
        for runtime_field in ("template", "config", "templateConfig"):
            runtime_value = recognition_config.get(runtime_field)
            if runtime_value is not None and not isinstance(runtime_value, dict):
                raise ValueError(f"recognitionConfig.{runtime_field} must be an object")
        for regions_field in ("regions", "archiveRegions"):
            runtime_regions = recognition_config.get(regions_field)
            if runtime_regions is not None:
                _validate_archive_regions(runtime_regions, f"recognitionConfig.{regions_field}")
        debug_artifacts = recognition_config.get("debugArtifacts")
        if debug_artifacts is not None and not isinstance(debug_artifacts, bool):
            raise ValueError("recognitionConfig.debugArtifacts must be a boolean")

        if "sheets" not in payload:
            raise ValueError("sheets is required")
        raw_sheets = payload["sheets"]
        if not isinstance(raw_sheets, list) or not raw_sheets:
            raise ValueError("sheets must be a non-empty list")
        sheets = [BatchSheetRequest.from_api_json(sheet, index=index) for index, sheet in enumerate(raw_sheets)]

        known_fields = {
            "examId",
            "callbackUrl",
            "externalBatchId",
            "templateCode",
            "schemaVersion",
            "templateVersion",
            "recognitionConfig",
            "sheets",
        }

        return cls(
            exam_id=exam_id,
            external_batch_id=external_batch_id,
            callback_url=callback_url,
            template_code=template_code,
            schema_version=schema_version,
            template_version=template_version,
            recognition_config=recognition_config,
            debug_artifacts=debug_artifacts,
            sheets=sheets,
            extra_fields={key: value for key, value in payload.items() if key not in known_fields},
        )

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "examId": self.exam_id,
            "recognitionConfig": self.recognition_config,
            "sheets": [sheet.to_api_dict() for sheet in self.sheets],
        }
        if self.callback_url is not None:
            payload["callbackUrl"] = self.callback_url
        if self.external_batch_id is not None:
            payload["externalBatchId"] = self.external_batch_id
        if self.template_code is not None:
            payload["templateCode"] = self.template_code
        if self.schema_version is not None:
            payload["schemaVersion"] = self.schema_version
        if self.template_version is not None:
            payload["templateVersion"] = self.template_version
        payload.update(self.extra_fields)
        return payload


@dataclass(frozen=True)
class ArtifactPayload:
    artifact_type: str
    osskey: str
    metadata: dict[str, Any] | None = None

    def to_callback_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"artifactType": self.artifact_type, "osskey": self.osskey}
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True)
class SheetRecognitionResult:
    sheet_id: str
    source_osskey: str
    status: str
    result: dict[str, Any] | list[Any]
    artifacts: list[ArtifactPayload] = field(default_factory=list)
    error: str | None = None

    def to_callback_dict(self) -> dict[str, Any]:
        result = self.result if isinstance(self.result, dict) else {}
        payload: dict[str, Any] = {
            "sheetId": self.sheet_id,
            "sourceOsskey": self.source_osskey,
            "status": self.status,
        }

        callback_fields = {
            "score": "score",
            "checkedImageOsskey": "checkedImageOsskey",
            "exam_id": "examNo",
            "examNo": "examNo",
            "file_id": "fileId",
            "fileId": "fileId",
            "review_required": "review_required",
            "weak_marks": "weak_marks",
        }
        for source_key, callback_key in callback_fields.items():
            if source_key in result and callback_key not in payload:
                payload[callback_key] = result[source_key]

        if "answers" in result:
            payload["answers"] = _compact_answers(result["answers"], self.artifacts)

        if "artifactErrors" in result:
            payload["artifactErrors"] = result["artifactErrors"]
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True)
class BatchRecognitionResult:
    task_id: str
    exam_id: str
    status: str
    sheets: list[SheetRecognitionResult]
    external_batch_id: str | None = None
    error: str | None = None
    artifacts: list[ArtifactPayload] = field(default_factory=list)
    aggregate_counts: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.aggregate_counts is None:
            object.__setattr__(self, "aggregate_counts", _aggregate_counts(self.sheets))

    def to_callback_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "taskId": self.task_id,
            "examId": self.exam_id,
            "status": self.status,
            "aggregateCounts": self.aggregate_counts,
            "sheets": [sheet.to_callback_dict() for sheet in self.sheets],
        }
        if self.external_batch_id is not None:
            payload["externalBatchId"] = self.external_batch_id
        if self.error is not None:
            payload["error"] = self.error
        return payload


def render_callback_payload_from_records(
    *,
    batch: dict[str, Any],
    sheets: list[dict[str, Any]],
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifacts = artifacts or []
    artifacts_by_sheet: dict[str, list[ArtifactPayload]] = {}
    batch_artifacts: list[ArtifactPayload] = []
    for artifact in artifacts:
        artifact_payload = ArtifactPayload(
            artifact_type=artifact["artifact_type"],
            osskey=artifact["osskey"],
            metadata=artifact.get("metadata_json"),
        )
        sheet_id = artifact.get("sheet_id")
        if sheet_id is None:
            batch_artifacts.append(artifact_payload)
        else:
            artifacts_by_sheet.setdefault(sheet_id, []).append(artifact_payload)

    sheet_results = [
        SheetRecognitionResult(
            sheet_id=sheet["sheet_id"],
            source_osskey=sheet["source_osskey"],
            status=sheet["status"],
            result=sheet.get("result_json") if sheet.get("result_json") is not None else {},
            artifacts=artifacts_by_sheet.get(sheet["sheet_id"], []),
            error=sheet.get("error"),
        )
        for sheet in sheets
    ]
    return BatchRecognitionResult(
        task_id=batch["task_id"],
        exam_id=batch["exam_id"],
        external_batch_id=batch.get("external_batch_id"),
        status=batch["status"],
        sheets=sheet_results,
        artifacts=batch_artifacts,
        error=batch.get("error"),
    ).to_callback_dict()


def _required_non_empty_string(payload: dict[str, Any], key: str, display_name: str) -> str:
    if key not in payload:
        raise ValueError(f"{display_name} is required")
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{display_name} must be a non-empty string")
    return value


def _required_non_empty_scalar(payload: dict[str, Any], key: str, display_name: str) -> str:
    if key not in payload:
        raise ValueError(f"{display_name} is required")
    value = payload[key]
    if isinstance(value, str):
        if value.strip():
            return value
    elif isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise ValueError(f"{display_name} must be a non-empty string")


def _optional_non_empty_string(value: Any, display_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{display_name} must be a non-empty string")
    return value


def _optional_template_version(value: Any, display_name: str) -> str | None:
    return _optional_template_path_component(value, display_name, example="v1")


def _optional_template_path_component(value: Any, display_name: str, *, example: str = "ASTS-HTTP-001") -> str | None:
    component = _optional_non_empty_string(value, display_name)
    if component is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", component):
        raise ValueError(f"{display_name} must be a safe template path component like {example}")
    if ".." in component:
        raise ValueError(f"{display_name} must be a safe template path component like {example}")
    return component


def _validate_archive_regions(value: Any, display_name: str) -> None:
    if isinstance(value, dict):
        if set(value.keys()) != {"archiveRegions"}:
            raise ValueError(f"{display_name} must be a list or an object with archiveRegions")
        value = value.get("archiveRegions")
    if not isinstance(value, list):
        raise ValueError(f"{display_name} must be a list or an object with archiveRegions")
    for index, region in enumerate(value):
        region_name = f"{display_name}[{index}]"
        if not isinstance(region, dict):
            raise ValueError(f"{region_name} must be an object")
        for key in ("regionCode", "regionName", "type"):
            if not isinstance(region.get(key), str) or not region[key].strip():
                raise ValueError(f"{region_name}.{key} must be a non-empty string")
        bbox = region.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"{region_name}.bbox must be a list of four numbers")
        for bbox_index, coordinate in enumerate(bbox):
            if isinstance(coordinate, bool) or not isinstance(coordinate, int | float):
                raise ValueError(f"{region_name}.bbox[{bbox_index}] must be a number")
        if bbox[2] <= 0 or bbox[3] <= 0:
            raise ValueError(f"{region_name}.bbox width and height must be positive")


def _aggregate_counts(sheets: list[SheetRecognitionResult]) -> dict[str, int]:
    counts: dict[str, int] = {"total": len(sheets)}
    for sheet in sheets:
        counts[sheet.status] = counts.get(sheet.status, 0) + 1
    return counts


def _compact_answers(answers: Any, artifacts: list[ArtifactPayload]) -> Any:
    if not isinstance(answers, list):
        return answers

    artifact_by_region: dict[str, ArtifactPayload] = {}
    for artifact in artifacts:
        if not _is_region_artifact(artifact):
            continue
        for key in _region_artifact_keys(artifact):
            existing = artifact_by_region.get(key)
            if existing is None or _region_artifact_area(artifact) > _region_artifact_area(existing):
                artifact_by_region[key] = artifact
    compact_answers = []
    for answer in answers:
        if not isinstance(answer, dict):
            compact_answers.append(answer)
            continue

        compact_region = {
            key: answer[key]
            for key in ("engine", "type", "regionCode", "regionName")
            if key in answer
        }
        if "engine" in compact_region:
            compact_region["engine"] = _compact_region_engine(compact_region["engine"])
        artifact = next(
            (artifact_by_region[key] for key in _answer_region_keys(answer) if key in artifact_by_region),
            None,
        )
        if artifact is not None:
            compact_region["osskey"] = artifact.osskey

        items = answer.get("items")
        if isinstance(items, list):
            compact_region["items"] = [
                _compact_answer_item(item)
                for item in items
                if isinstance(item, dict)
            ]
        elif "items" in answer:
            compact_region["items"] = items
        compact_answers.append(compact_region)
    return compact_answers


def _compact_answer_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in ("field", "value", "confidence")
        if key in item
    }


def _compact_region_engine(engine: Any) -> str:
    if str(engine).strip().lower() in {"paddleocr", "ocr"}:
        return "ocr"
    return "omr"


def _answer_region_keys(answer: dict[str, Any]) -> list[str]:
    values = [answer.get("regionCode"), answer.get("type"), answer.get("regionName")]
    return _region_match_keys(values)


def _region_artifact_keys(artifact: ArtifactPayload) -> list[str]:
    metadata = artifact.metadata or {}
    values = [
        metadata.get("regionCode"),
        metadata.get("regionType"),
        metadata.get("type"),
        metadata.get("regionName"),
        artifact.artifact_type,
    ]
    return _region_match_keys(values)


def _region_artifact_area(artifact: ArtifactPayload) -> int:
    metadata = artifact.metadata or {}
    bbox = metadata.get("bbox")
    if isinstance(bbox, dict):
        width = bbox.get("width")
        height = bbox.get("height")
    elif isinstance(bbox, list) and len(bbox) == 4:
        width = bbox[2]
        height = bbox[3]
    else:
        return 0
    if not isinstance(width, int | float) or not isinstance(height, int | float):
        return 0
    if width <= 0 or height <= 0:
        return 0
    return int(width * height)


def _region_match_keys(values: list[Any]) -> list[str]:
    keys: list[str] = []
    for value in values:
        normalized = _normalize_region_key(value)
        if normalized and normalized not in keys:
            keys.append(normalized)
        for alias in _business_region_aliases(normalized):
            if alias not in keys:
                keys.append(alias)
    return keys


def _normalize_region_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _business_region_aliases(normalized: str) -> tuple[str, ...]:
    if normalized in {"multichoice", "multiplechoice", "multiplechoicearea", "multichoicearea"}:
        return ("multiplechoice", "multichoice")
    if "fill" in normalized or "填空" in normalized:
        return ("fillbank", "fillblank")
    if "solution" in normalized or "解答" in normalized:
        return ("solution",)
    return ()


def _is_region_artifact(artifact: ArtifactPayload) -> bool:
    metadata = artifact.metadata or {}
    return "regionCode" in metadata
