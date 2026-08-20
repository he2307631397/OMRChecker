from __future__ import annotations

import shutil
import uuid
import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Protocol

from .batch_models import (
    BatchRecognitionRequest,
    BatchRecognitionResult,
    SheetRecognitionResult,
)
from .cos_client import ObjectStorageClient
from .service_config import ServiceConfig
from .task_store import TaskStore

_SAFE_COMPONENT_PATTERN = re.compile(r"[^\w\u4e00-\u9fff.-]+", re.UNICODE)


@dataclass(frozen=True)
class RecognitionOutput:
    result: dict | list


@dataclass(frozen=True)
class RecognitionContext:
    task_id: str
    sheet: object
    source_path: Path
    workdir: Path
    request: BatchRecognitionRequest
    template_dir: Path | None = None


RecognitionRunner = Callable[[RecognitionContext], RecognitionOutput]


class CallbackClient(Protocol):
    def send(self, payload: dict) -> object:
        ...


class BatchRecognitionService:
    def __init__(
        self,
        *,
        store: TaskStore,
        object_storage: ObjectStorageClient,
        config: ServiceConfig,
        recognition_runner: RecognitionRunner | None = None,
        callback_client: CallbackClient | None = None,
        task_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.object_storage = object_storage
        self.config = config
        self.recognition_runner = recognition_runner or _default_recognition_runner
        self.callback_client = callback_client
        self.task_id_factory = task_id_factory or (lambda: uuid.uuid4().hex)

    def submit_batch(self, request: BatchRecognitionRequest) -> BatchRecognitionResult:
        task_id = self.task_id_factory()
        callback_url = request.callback_url or self.config.callback.url
        self.store.create_batch(
            task_id=task_id,
            exam_id=request.exam_id,
            external_batch_id=request.external_batch_id,
            status="pending",
            callback_url=callback_url,
            request_json=request.to_api_dict(),
        )
        for sheet in request.sheets:
            self.store.create_sheet(
                task_id=task_id,
                sheet_id=sheet.sheet_id,
                source_osskey=sheet.osskey,
                status="pending",
                result_json={},
            )
        return self._result_from_store(task_id)

    def process_batch(self, task_id: str) -> BatchRecognitionResult:
        batch = self._require_batch(task_id)
        request = BatchRecognitionRequest.from_api_json(batch["request_json"])
        preserve_debug_artifacts = self._should_preserve_debug_artifacts(request)
        sheet_workdirs: dict[str, Path] = {}
        self.store.update_batch_status(task_id, "running")
        self._persist_request_template_dependencies(request)

        for sheet_request in request.sheets:
            self.store.update_sheet(
                task_id=task_id,
                sheet_id=sheet_request.sheet_id,
                source_osskey=sheet_request.osskey,
                status="running",
                result_json={},
            )
            workdir = self._sheet_workdir(task_id, sheet_request.sheet_id)
            sheet_workdirs[sheet_request.sheet_id] = workdir
            try:
                source_path = workdir / "source" / Path(sheet_request.osskey).name
                self.object_storage.download_file(sheet_request.osskey, source_path)
                self._copy_template_dependencies(request, workdir)
                if not self._uses_central_template_config(request):
                    self._write_request_template_dependencies(request, workdir)
                output = self.recognition_runner(
                    RecognitionContext(
                        task_id=task_id,
                        sheet=sheet_request,
                        source_path=source_path,
                        workdir=workdir,
                        request=request,
                        template_dir=self._template_dependency_dir(request).resolve(strict=False)
                        if self._uses_central_template_config(request)
                        else None,
                    )
                )
                result_json = output.result
                if isinstance(result_json, dict):
                    stored_result = dict(result_json)
                else:
                    stored_result = result_json

                self.store.update_sheet(
                    task_id=task_id,
                    sheet_id=sheet_request.sheet_id,
                    source_osskey=sheet_request.osskey,
                    status="completed",
                    result_json=stored_result,
                )
            except Exception as exc:  # noqa: BLE001 - per-sheet isolation is intentional.
                self.store.update_sheet(
                    task_id=task_id,
                    sheet_id=sheet_request.sheet_id,
                    source_osskey=sheet_request.osskey,
                    status="failed",
                    result_json={},
                    error=str(exc),
                )

        status = self._compute_batch_status(task_id)
        result = self._result_from_store(task_id, status=status)
        self.store.update_batch_status(task_id, status, result_json=result.to_callback_dict())
        if not preserve_debug_artifacts:
            self._cleanup_sheet_workdirs(task_id, sheet_workdirs)
        final_result = self._result_from_store(task_id)
        self._send_callback_if_configured(batch, final_result)
        return final_result

    def _should_preserve_debug_artifacts(self, request: BatchRecognitionRequest) -> bool:
        if request.debug_artifacts is not None:
            return request.debug_artifacts
        return self.config.recognition.debug_artifacts

    def _cleanup_sheet_workdirs(self, task_id: str, sheet_workdirs: dict[str, Path]) -> None:
        for sheet_id, workdir in sheet_workdirs.items():
            try:
                shutil.rmtree(workdir)
            except FileNotFoundError:
                continue
            except Exception as exc:  # noqa: BLE001 - cleanup must not fail recognition.
                self._record_cleanup_error(task_id, sheet_id, str(exc))

    def _record_cleanup_error(self, task_id: str, sheet_id: str, error: str) -> None:
        sheet = next((item for item in self.store.list_sheets(task_id) if item["sheet_id"] == sheet_id), None)
        if sheet is None:
            return
        result_json = sheet.get("result_json") or {}
        if isinstance(result_json, dict):
            stored_result = dict(result_json)
            stored_result["artifactCleanupError"] = error
        else:
            stored_result = {"result": result_json, "artifactCleanupError": error}
        self.store.update_sheet(
            task_id=task_id,
            sheet_id=sheet_id,
            source_osskey=sheet["source_osskey"],
            status=sheet["status"],
            result_json=stored_result,
            error=sheet.get("error"),
        )

    def _send_callback_if_configured(self, batch: dict, result: BatchRecognitionResult) -> None:
        target_url = batch.get("callback_url") or self.config.callback.url
        if self.callback_client is None or not target_url:
            return

        payload = result.to_callback_dict()
        try:
            response = self.callback_client.send(payload)
            response_data = response if isinstance(response, dict) else {}
            self.store.add_callback_attempt(
                task_id=result.task_id,
                target_url=target_url,
                status_code=response_data.get("status_code"),
                success=bool(response_data.get("success", True)),
                error=response_data.get("error"),
                request_json=payload,
                response_text=response_data.get("response_text"),
            )
        except Exception as exc:  # noqa: BLE001 - callback failure must be recorded, not raised.
            self.store.add_callback_attempt(
                task_id=result.task_id,
                target_url=target_url,
                success=False,
                error=str(exc),
                request_json=payload,
            )

    def _copy_template_dependencies(self, request: BatchRecognitionRequest, workdir: Path) -> None:
        template_dir = self._template_dependency_dir(request)
        if not template_dir.exists():
            return
        resolved_template_dir = template_dir.resolve(strict=False)
        for source in template_dir.iterdir():
            if source.is_symlink():
                continue
            resolved_source = source.resolve(strict=False)
            if resolved_template_dir != resolved_source and resolved_template_dir not in resolved_source.parents:
                continue
            if source.is_file():
                if self._uses_central_template_config(request) and source.name in {"config.json", "template.json", "evaluation.json"}:
                    continue
                shutil.copy2(source, workdir / source.name)

    def _template_dependency_dir(self, request: BatchRecognitionRequest) -> Path:
        if request.template_code is not None:
            schema_version = request.schema_version or request.template_version or "v1"
            return _safe_config_dependency_dir(request.template_code, schema_version)
        if request.template_version is None:
            return self.config.storage.template_dir
        return _safe_config_dependency_dir(request.template_version)

    def _uses_central_template_config(self, request: BatchRecognitionRequest) -> bool:
        return request.template_code is not None or request.template_version is not None

    def _persist_request_template_dependencies(self, request: BatchRecognitionRequest) -> None:
        if not self._uses_central_template_config(request):
            return
        template_dir = self._template_dependency_dir(request)
        self._write_request_template_dependencies(request, template_dir)
        if not (template_dir / "template.json").exists():
            raise ValueError(
                f"template.json is required for templateCode/schemaVersion recognition: {template_dir / 'template.json'}. "
                "Provide a complete recognitionConfig.templateConfig/template payload or pre-create template.json in that directory."
            )

    def _write_request_template_dependencies(self, request: BatchRecognitionRequest, workdir: Path) -> None:
        template = request.recognition_config.get("template")
        if template is None:
            template = request.recognition_config.get("templateConfig")
        config = request.recognition_config.get("config")
        if isinstance(template, dict):
            normalized_template = _drop_none_values(template)
            if normalized_template:
                normalized_template = self._materialize_template_reference_images(normalized_template, workdir)
                _write_json(workdir / "template.json", normalized_template)
        if isinstance(config, dict):
            _write_json(workdir / "config.json", _normalize_runtime_config(config))

    def _materialize_template_reference_images(self, template: dict, workdir: Path) -> dict:
        """Download FeatureBasedAlignment reference images from object storage.

        Java callers may pass an OSS key in
        ``templateConfig.preProcessors[].options.reference``. OMRChecker expects
        that value to be a local file name relative to the template/work
        directory, so remote references are downloaded and the generated
        template is rewritten to the local file name. Existing local files such
        as ``reference.png`` are left unchanged.
        """

        pre_processors = template.get("preProcessors")
        if not isinstance(pre_processors, list):
            return template

        rewritten_template = dict(template)
        rewritten_pre_processors = []
        changed = False
        downloaded_names: dict[str, str] = {}
        used_local_names: set[str] = set()
        for index, pre_processor in enumerate(pre_processors):
            if not isinstance(pre_processor, dict):
                rewritten_pre_processors.append(pre_processor)
                continue

            options = pre_processor.get("options")
            if not isinstance(options, dict):
                rewritten_pre_processors.append(pre_processor)
                continue

            reference = options.get("reference")
            if not isinstance(reference, str) or not reference.strip():
                rewritten_options, removed_metadata = _strip_template_reference_metadata(options)
                if removed_metadata:
                    changed = True
                    rewritten_pre_processor = dict(pre_processor)
                    rewritten_pre_processor["options"] = rewritten_options
                    rewritten_pre_processors.append(rewritten_pre_processor)
                else:
                    rewritten_pre_processors.append(pre_processor)
                continue

            rewritten_options, removed_metadata = _strip_template_reference_metadata(options)
            local_reference = self._materialize_reference_image(
                reference.strip(),
                workdir,
                index=index,
                name_map=downloaded_names,
                used_local_names=used_local_names,
            )
            if local_reference == reference and not removed_metadata:
                rewritten_pre_processors.append(pre_processor)
                continue

            changed = True
            rewritten_options["reference"] = local_reference
            rewritten_pre_processor = dict(pre_processor)
            rewritten_pre_processor["options"] = rewritten_options
            rewritten_pre_processors.append(rewritten_pre_processor)

        if not changed:
            return template
        rewritten_template["preProcessors"] = rewritten_pre_processors
        return rewritten_template

    def _materialize_reference_image(
        self,
        reference: str,
        workdir: Path,
        *,
        index: int,
        name_map: dict[str, str],
        used_local_names: set[str],
    ) -> str:
        reference_path = Path(reference)
        if _is_local_template_reference(reference_path) and (workdir / reference_path).is_file():
            used_local_names.add(reference)
            return reference
        if reference in name_map:
            return name_map[reference]

        local_name = _safe_reference_filename(reference, index=index, used_names=used_local_names)
        destination = workdir / local_name
        self.object_storage.download_file(reference, destination)
        name_map[reference] = local_name
        used_local_names.add(local_name)
        return local_name

    def _sheet_workdir(self, task_id: str, sheet_id: str) -> Path:
        workdir = self.config.storage.service_data_dir / "tasks" / _safe_component(task_id) / "sheets" / _safe_component(sheet_id)
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _compute_batch_status(self, task_id: str) -> str:
        sheets = self.store.list_sheets(task_id)
        completed = sum(1 for sheet in sheets if sheet["status"] == "completed")
        failed = sum(1 for sheet in sheets if sheet["status"] == "failed")
        if failed == 0:
            return "completed"
        if completed == 0:
            return "failed"
        return "partial_failed"

    def _result_from_store(self, task_id: str, *, status: str | None = None) -> BatchRecognitionResult:
        batch = self._require_batch(task_id)
        sheets = self.store.list_sheets(task_id)
        sheet_results = []
        for sheet in sheets:
            sheet_results.append(
                SheetRecognitionResult(
                    sheet_id=sheet["sheet_id"],
                    source_osskey=sheet["source_osskey"],
                    status=sheet["status"],
                    result=sheet.get("result_json") or {},
                    error=sheet.get("error"),
                )
            )
        return BatchRecognitionResult(
            task_id=task_id,
            exam_id=batch["exam_id"],
            external_batch_id=batch.get("external_batch_id"),
            status=status or batch["status"],
            sheets=sheet_results,
            error=batch.get("error"),
        )

    def _require_batch(self, task_id: str) -> dict:
        batch = self.store.get_batch(task_id)
        if batch is None:
            raise KeyError(f"batch not found: {task_id}")
        return batch


def _default_recognition_runner(context: RecognitionContext) -> RecognitionOutput:
    raise RuntimeError(
        "No default OMR recognition runner is configured for BatchRecognitionService. "
        "Pass recognition_runner when constructing the service."
    )


def _safe_component(value: str) -> str:
    sanitized = _SAFE_COMPONENT_PATTERN.sub("_", value.strip())
    sanitized = sanitized.replace("/", "_").replace("\\", "_")
    sanitized = sanitized.replace("..", "_")
    sanitized = re.sub(r"_+", "_", sanitized).strip("._")
    return sanitized or "item"


def _safe_config_dependency_dir(*parts: str) -> Path:
    config_root = Path("config")
    dependency_dir = config_root.joinpath(*parts)
    resolved_config_root = config_root.resolve(strict=False)
    resolved_dependency_dir = dependency_dir.resolve(strict=False)
    if resolved_config_root != resolved_dependency_dir and resolved_config_root not in resolved_dependency_dir.parents:
        raise ValueError(f"template dependency directory is outside config directory: {dependency_dir}")
    return dependency_dir


def _is_local_template_reference(path: Path) -> bool:
    return not path.is_absolute() and not path.drive and len(path.parts) == 1 and path.name not in {"", ".", ".."}


def _strip_template_reference_metadata(options: dict) -> tuple[dict, bool]:
    """Remove Java/business-only reference metadata before schema validation.

    OMRChecker's FeatureBasedAlignment schema only accepts runtime options such
    as ``reference``. API callers may include metadata like ``referenceFileId``
    and ``referenceName`` for their own asset records, but those keys must not be
    persisted into template.json because OMRChecker validates preProcessor
    options with ``additionalProperties: false``.
    """

    rewritten = dict(options)
    removed = False
    for key in ("referenceFileId", "referenceName"):
        if key in rewritten:
            rewritten.pop(key, None)
            removed = True
    return rewritten, removed


def _safe_reference_filename(reference: str, *, index: int, used_names: set[str]) -> str:
    name = Path(reference).name.strip()
    if not name or name in {".", ".."}:
        name = f"reference_{index + 1}.png"
    sanitized = _SAFE_COMPONENT_PATTERN.sub("_", name)
    sanitized = sanitized.replace("..", "_").strip("._")
    if not sanitized:
        sanitized = f"reference_{index + 1}.png"
    if sanitized not in used_names:
        return sanitized
    stem = Path(sanitized).stem or "reference"
    suffix = Path(sanitized).suffix or ".png"
    counter = index + 1
    while True:
        candidate = f"{stem}_{counter}{suffix}"
        if candidate not in used_names:
            return candidate
        counter += 1


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_runtime_config(config: dict) -> dict:
    """Convert Java/API camelCase config keys to OMRChecker config keys.

    The public batch API accepts Java-friendly keys like ``displayHeight`` and
    ``thresholdParams``. OMRChecker's runtime ``config.json`` expects snake_case
    section names and, for threshold constants, uppercase names. Existing native
    OMRChecker keys are preserved so callers can still pass config files as-is.
    """

    section_maps = {
        "dimensions": {
            "displayHeight": "display_height",
            "displayWidth": "display_width",
            "processingHeight": "processing_height",
            "processingWidth": "processing_width",
        },
        "outputs": {
            "showImageLevel": "show_image_level",
            "saveImageLevel": "save_image_level",
            "saveDetections": "save_detections",
            "filterOutMultimarkedFiles": "filter_out_multimarked_files",
        },
        "threshold_params": {
            "gammaLow": "GAMMA_LOW",
            "minGap": "MIN_GAP",
            "minJump": "MIN_JUMP",
            "confidentSurplus": "CONFIDENT_SURPLUS",
            "jumpDelta": "JUMP_DELTA",
            "pageTypeForThreshold": "PAGE_TYPE_FOR_THRESHOLD",
        },
        "alignment_params": {
            "autoAlign": "auto_align",
            "matchCol": "match_col",
            "maxSteps": "max_steps",
        },
        "pdf_params": {
            "pdfDpi": "pdf_dpi",
            "pdfPage": "pdf_page",
        },
        "weak_mark_params": {
            "minGap": "min_gap",
            "minDeltaFromBlank": "min_delta_from_blank",
            "adaptiveMinDeltaFromBlank": "adaptive_min_delta_from_blank",
            "minDeltaFromPageBlank": "min_delta_from_page_blank",
            "minPageZScore": "min_page_z_score",
            "minDarkPixelRatio": "min_dark_pixel_ratio",
            "minDensityGap": "min_density_gap",
            "resolveSingleChoiceConflicts": "resolve_single_choice_conflicts",
            "conflictMinGap": "conflict_min_gap",
            "conflictMinDeltaFromBlank": "conflict_min_delta_from_blank",
            "conflictAutoResolveMinConfidence": "conflict_auto_resolve_min_confidence",
            "conflictReviewMinConfidence": "conflict_review_min_confidence",
            "weakFillAutoResolveMinConfidence": "weak_fill_auto_resolve_min_confidence",
            "weakFillReviewMinConfidence": "weak_fill_review_min_confidence",
            "maxMean": "max_mean",
            "supportedFieldTypes": "supported_field_types",
            "excludeLabels": "exclude_labels",
        },
        "weak_identifier_params": {
            "excludeLabels": "exclude_labels",
            "resolveConflicts": "resolve_conflicts",
            "conflictAutoResolveMinConfidence": "conflict_auto_resolve_min_confidence",
            "conflictReviewMinConfidence": "conflict_review_min_confidence",
            "minGap": "min_gap",
            "minDeltaFromBlank": "min_delta_from_blank",
            "adaptiveMinGap": "adaptive_min_gap",
            "adaptiveMinDeltaFromBlank": "adaptive_min_delta_from_blank",
            "minPageZScore": "min_page_z_score",
            "minDarkPixelRatio": "min_dark_pixel_ratio",
            "minDensityGap": "min_density_gap",
            "maxMean": "max_mean",
            "adaptiveMaxMean": "adaptive_max_mean",
            "supportedFieldTypes": "supported_field_types",
        },
        "weak_multi_mark_params": {
            "onlyWhenBlank": "only_when_blank",
            "minDeltaFromBlank": "min_delta_from_blank",
            "maxMean": "max_mean",
            "maxMarks": "max_marks",
            "fullSelectFallbackEnabled": "full_select_fallback_enabled",
            "fullSelectMaxMean": "full_select_max_mean",
            "fullSelectMinDeltaFromBlank": "full_select_min_delta_from_blank",
            "fullSelectMaxSpread": "full_select_max_spread",
        },
    }
    top_level_sections = {
        "thresholdParams": "threshold_params",
        "alignmentParams": "alignment_params",
        "pdfParams": "pdf_params",
        "weakMarkParams": "weak_mark_params",
        "weakIdentifierParams": "weak_identifier_params",
        "weakMultiMarkParams": "weak_multi_mark_params",
    }

    normalized = _drop_none_values(config)
    for api_key, runtime_key in top_level_sections.items():
        if api_key in normalized:
            api_value = normalized.pop(api_key)
            if runtime_key not in normalized:
                normalized[runtime_key] = api_value
    for section, key_map in section_maps.items():
        value = normalized.get(section)
        if isinstance(value, dict):
            normalized[section] = _rename_keys(value, key_map)
    _coerce_integer_like_paths(
        normalized,
        {
            ("dimensions", "display_height"),
            ("dimensions", "display_width"),
            ("dimensions", "processing_height"),
            ("dimensions", "processing_width"),
            ("outputs", "show_image_level"),
            ("outputs", "save_image_level"),
            ("threshold_params", "MIN_GAP"),
            ("threshold_params", "MIN_JUMP"),
            ("threshold_params", "CONFIDENT_SURPLUS"),
            ("threshold_params", "JUMP_DELTA"),
            ("alignment_params", "match_col"),
            ("alignment_params", "max_steps"),
            ("alignment_params", "stride"),
            ("alignment_params", "thickness"),
            ("pdf_params", "pdf_dpi"),
            ("pdf_params", "pdf_page"),
            ("weak_multi_mark_params", "max_marks"),
        },
    )
    return normalized


def _drop_none_values(value):
    if isinstance(value, dict):
        return {key: _drop_none_values(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none_values(item) for item in value]
    return value


def _coerce_integer_like_paths(payload: dict, paths: set[tuple[str, str]]) -> None:
    for section, key in paths:
        section_value = payload.get(section)
        if not isinstance(section_value, dict) or key not in section_value:
            continue
        value = section_value[key]
        if isinstance(value, float) and value.is_integer():
            section_value[key] = int(value)


def _rename_keys(payload: dict, key_map: dict[str, str]) -> dict:
    renamed = dict(payload)
    for api_key, runtime_key in key_map.items():
        if api_key in renamed:
            api_value = renamed.pop(api_key)
            if runtime_key not in renamed:
                renamed[runtime_key] = api_value
    return renamed
