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
        result = self.result
        if isinstance(result, dict) and "checkedImageOsskey" in result:
            result = {
                key: value
                for key, value in result.items()
                if key != "checkedImageOsskey"
            }
        payload: dict[str, Any] = {
            "sheetId": self.sheet_id,
            "osskey": self.source_osskey,
            "sourceOsskey": self.source_osskey,
            "status": self.status,
            "result": result,
            "artifacts": [artifact.to_callback_dict() for artifact in self.artifacts],
        }
        if isinstance(self.result, dict):
            for key, value in self.result.items():
                payload.setdefault(key, value)
        region_images = [
            _region_image_payload(artifact)
            for artifact in self.artifacts
            if _is_region_artifact(artifact)
        ]
        if region_images:
            payload["regionImages"] = region_images
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
        if self.artifacts:
            payload["artifacts"] = [artifact.to_callback_dict() for artifact in self.artifacts]
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


def _aggregate_counts(sheets: list[SheetRecognitionResult]) -> dict[str, int]:
    counts: dict[str, int] = {"total": len(sheets)}
    for sheet in sheets:
        counts[sheet.status] = counts.get(sheet.status, 0) + 1
    return counts


def _is_region_artifact(artifact: ArtifactPayload) -> bool:
    metadata = artifact.metadata or {}
    return "regionCode" in metadata


def _region_image_payload(artifact: ArtifactPayload) -> dict[str, Any]:
    metadata = artifact.metadata or {}
    payload: dict[str, Any] = {
        "osskey": artifact.osskey,
        "uploadStatus": "uploaded",
    }
    if "regionCode" in metadata:
        payload["regionCode"] = metadata["regionCode"]
    if "regionName" in metadata:
        payload["regionName"] = metadata["regionName"]
    if "regionType" in metadata:
        payload["type"] = metadata["regionType"]
    if "bbox" in metadata:
        payload["bbox"] = metadata["bbox"]
    return payload
