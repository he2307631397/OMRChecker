from __future__ import annotations

import cv2
import numpy as np
import shutil
import uuid
import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Protocol, Sequence

from .batch_models import (
    ArtifactPayload,
    BatchRecognitionRequest,
    BatchRecognitionResult,
    SheetRecognitionResult,
)
from .cos_client import ObjectStorageClient
from .region_artifacts import generate_region_artifacts, load_template_archive_regions
from .service_config import ServiceConfig
from .task_store import TaskStore

_SAFE_COMPONENT_PATTERN = re.compile(r"[^\w\u4e00-\u9fff.-]+", re.UNICODE)


@dataclass(frozen=True)
class RecognitionOutput:
    result: dict | list
    checked_image_path: Path | None = None


@dataclass(frozen=True)
class RecognitionContext:
    task_id: str
    sheet: object
    source_path: Path
    workdir: Path
    request: BatchRecognitionRequest
    template_dir: Path | None = None


RecognitionRunner = Callable[[RecognitionContext], RecognitionOutput]
RegionArtifactGenerator = Callable[..., list[ArtifactPayload]]


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
        region_artifact_generator: RegionArtifactGenerator | None = None,
        task_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.object_storage = object_storage
        self.config = config
        self.recognition_runner = recognition_runner or _default_recognition_runner
        self.callback_client = callback_client
        self.region_artifact_generator = region_artifact_generator or generate_region_artifacts
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
        return self._process_batch_sheets(task_id)

    def retry_failed_sheets(self, task_id: str) -> BatchRecognitionResult:
        failed_sheet_ids = [sheet["sheet_id"] for sheet in self.store.list_sheets(task_id) if sheet["status"] == "failed"]
        if not failed_sheet_ids:
            return self._result_from_store(task_id)
        return self._process_batch_sheets(task_id, sheet_ids=failed_sheet_ids)

    def _process_batch_sheets(self, task_id: str, sheet_ids: Sequence[str] | None = None) -> BatchRecognitionResult:
        batch = self._require_batch(task_id)
        request = BatchRecognitionRequest.from_api_json(batch["request_json"])
        preserve_debug_artifacts = self._should_preserve_debug_artifacts(request)
        sheet_workdirs: dict[str, Path] = {}
        self.store.update_batch_status(task_id, "running")
        self._persist_request_template_dependencies(request)

        any_artifact_errors = False
        selected_sheet_ids = set(sheet_ids) if sheet_ids is not None else None
        for sheet_request in request.sheets:
            if selected_sheet_ids is not None and sheet_request.sheet_id not in selected_sheet_ids:
                continue
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

                artifact_errors = []
                if output.checked_image_path is not None and isinstance(stored_result, dict):
                    checked_image_osskey, checked_image_error = self._upload_checked_image(
                        task_id,
                        sheet_request.sheet_id,
                        output.checked_image_path,
                    )
                    if checked_image_osskey is not None:
                        stored_result["checkedImageOsskey"] = checked_image_osskey
                    if checked_image_error is not None:
                        artifact_errors.append(checked_image_error)
                        any_artifact_errors = True
                archive_regions = self._archive_regions_for_request(request)
                if output.checked_image_path is not None and archive_regions:
                    local_artifacts = self.region_artifact_generator(
                        output.checked_image_path,
                        archive_regions,
                        workdir / "region_artifacts",
                        sheet_id=sheet_request.sheet_id,
                        task_id=task_id,
                    )
                    uploaded, region_artifact_errors = self._upload_region_artifacts(
                        task_id,
                        sheet_request.sheet_id,
                        local_artifacts,
                        workdir / "region_artifacts",
                    )
                    artifact_errors.extend(region_artifact_errors)
                    if artifact_errors:
                        any_artifact_errors = True

                if isinstance(stored_result, dict) and artifact_errors:
                    stored_result["artifactErrors"] = artifact_errors

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

        status = self._compute_batch_status(task_id, artifact_errors=any_artifact_errors)
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

    def _upload_region_artifacts(
        self,
        task_id: str,
        sheet_id: str,
        local_artifacts: list[ArtifactPayload],
        region_output_dir: Path,
    ) -> tuple[list[ArtifactPayload], list[dict]]:
        uploaded: list[ArtifactPayload] = []
        errors: list[dict] = []
        for artifact in local_artifacts:
            metadata = dict(artifact.metadata or {})
            local_path = Path(str(metadata.get("localPath", artifact.osskey)))
            remote_key = f"artifacts/{_safe_component(task_id)}/{_safe_component(sheet_id)}/{local_path.name}"
            try:
                _ensure_within_directory(local_path, region_output_dir)
                self.object_storage.upload_file(local_path, remote_key, content_type="image/png")
            except Exception as exc:  # noqa: BLE001 - artifact upload is intentionally non-fatal.
                errors.append(
                    {
                        "artifactType": artifact.artifact_type,
                        "localPath": str(local_path),
                        "osskey": remote_key,
                        "error": str(exc),
                    }
                )
                continue

            remote_artifact = ArtifactPayload(
                artifact_type=artifact.artifact_type,
                osskey=remote_key,
                metadata=metadata,
            )
            uploaded.append(remote_artifact)
            self.store.add_artifact(
                task_id=task_id,
                sheet_id=sheet_id,
                artifact_type=remote_artifact.artifact_type,
                osskey=remote_key,
                local_path=str(local_path),
                metadata_json=metadata,
            )
        return uploaded, errors

    def _upload_checked_image(self, task_id: str, sheet_id: str, checked_image_path: Path) -> tuple[str | None, dict | None]:
        remote_key = f"checked/{_safe_component(task_id)}/{_safe_component(sheet_id)}/{checked_image_path.name}"
        try:
            self.object_storage.upload_file(checked_image_path, remote_key, content_type="image/png")
        except Exception as exc:  # noqa: BLE001 - checked-image upload is non-fatal like region artifacts.
            return None, {
                "artifactType": "checked_image",
                "localPath": str(checked_image_path),
                "osskey": remote_key,
                "error": str(exc),
            }
        return remote_key, None

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

    def _archive_regions_for_request(self, request: BatchRecognitionRequest):
        if self._uses_central_template_config(request):
            template_regions = load_template_archive_regions(self._template_dependency_dir(request))
            if template_regions:
                return template_regions
        return self.config.archive_regions

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
        archive_regions = _runtime_archive_regions(request.recognition_config)
        generated_template_options = self._materialize_generated_template_assets(request.recognition_config, workdir)
        if generated_template_options:
            template = _ensure_template_preprocessors(template if isinstance(template, dict) else {}, generated_template_options)
        if isinstance(template, dict):
            normalized_template = _drop_none_values(template)
            if normalized_template:
                normalized_template = self._materialize_template_reference_images(normalized_template, workdir)
                template_path = workdir / "template.json"
                _write_json(template_path, _merge_json_file(template_path, normalized_template))
        if isinstance(config, dict):
            _write_json(workdir / "config.json", _normalize_runtime_config(config))
        if archive_regions is not None:
            _write_json(workdir / "regions.json", archive_regions)

    def _materialize_template_reference_images(self, template: dict, workdir: Path) -> dict:
        """Download preProcessor reference images from object storage into the template dir.

        Runtime template payloads may carry an OSS key in
        ``preProcessors[].options.reference``. OMRChecker expects that value to be
        a local file name under the template/work directory, so remote keys are
        downloaded and the template reference is rewritten to the local name.
        Existing local references such as ``reference.png`` are left unchanged.
        """

        pre_processors = template.get("preProcessors")
        if not isinstance(pre_processors, list):
            return template

        rewritten_template = dict(template)
        rewritten_pre_processors = []
        changed = False
        remote_reference_names: dict[str, str] = {}
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
                rewritten_pre_processors.append(pre_processor)
                continue

            local_reference = self._materialize_reference_image(reference.strip(), workdir, index=index, name_map=remote_reference_names)
            if local_reference == reference:
                rewritten_pre_processors.append(pre_processor)
                continue

            changed = True
            rewritten_options = dict(options)
            rewritten_options["reference"] = local_reference
            rewritten_pre_processor = dict(pre_processor)
            rewritten_pre_processor["options"] = rewritten_options
            rewritten_pre_processors.append(rewritten_pre_processor)

        if not changed:
            return template
        rewritten_template["preProcessors"] = rewritten_pre_processors
        return rewritten_template

    def _materialize_reference_image(self, reference: str, workdir: Path, *, index: int, name_map: dict[str, str]) -> str:
        reference_path = Path(reference)
        if _is_local_template_reference(reference_path) and (workdir / reference_path).is_file():
            return reference
        if reference in name_map:
            return name_map[reference]

        local_name = _safe_reference_filename(reference, index=index)
        destination = workdir / local_name
        self.object_storage.download_file(reference, destination)
        name_map[reference] = local_name
        return local_name

    def _materialize_generated_template_assets(self, recognition_config: dict, workdir: Path) -> list[dict]:
        marker_config = recognition_config.get("markerConfig")
        reference_config = recognition_config.get("referenceConfig")
        generated_pre_processors: list[dict] = []

        if isinstance(marker_config, dict):
            marker_options = self._materialize_marker_config(marker_config, workdir)
            if marker_config.get("enableCropOnMarkers") is True:
                generated_pre_processors.append({"name": "CropOnMarkers", "options": marker_options})

        if isinstance(reference_config, dict):
            reference_options = self._materialize_reference_config(reference_config, workdir)
            generated_pre_processors.append({"name": "FeatureBasedAlignment", "options": reference_options})
        elif isinstance(marker_config, dict):
            reference_options = self._materialize_reference_config(
                {
                    "sourcePdfOsskey": marker_config.get("sourcePdfOsskey"),
                    "pdfPage": marker_config.get("pdfPage", 1),
                    "pdfDpi": marker_config.get("pdfDpi", 144),
                    "outputName": "reference.png",
                },
                workdir,
            )
            generated_pre_processors.append({"name": "FeatureBasedAlignment", "options": reference_options})

        return generated_pre_processors

    def _materialize_marker_config(self, marker_config: dict, workdir: Path) -> dict:
        source_pdf = _required_config_string(marker_config, "sourcePdfOsskey", "markerConfig.sourcePdfOsskey")
        pdf_page = _positive_int_config(marker_config.get("pdfPage", 1), "markerConfig.pdfPage")
        pdf_dpi = _positive_int_config(marker_config.get("pdfDpi", 144), "markerConfig.pdfDpi")
        bbox = _bbox_config(marker_config.get("bbox"), "markerConfig.bbox")
        output_name = _safe_template_asset_name(marker_config.get("outputName") or "marker.png", default="marker.png")

        rendered = self._render_pdf_from_object(source_pdf, workdir, pdf_page=pdf_page, pdf_dpi=pdf_dpi)
        x, y, width, height = _clamped_bbox(bbox, rendered.shape[1], rendered.shape[0], "markerConfig.bbox")
        marker = rendered[y : y + height, x : x + width]
        destination = workdir / output_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), marker):
            raise ValueError(f"unable to write generated marker image: {destination}")

        options = {"relativePath": output_name}
        pre_processor_options = marker_config.get("preProcessorOptions")
        if isinstance(pre_processor_options, dict):
            options.update(_drop_none_values(pre_processor_options))
        return options

    def _materialize_reference_config(self, reference_config: dict, workdir: Path) -> dict:
        source_pdf = _required_config_string(reference_config, "sourcePdfOsskey", "referenceConfig.sourcePdfOsskey")
        pdf_page = _positive_int_config(reference_config.get("pdfPage", 1), "referenceConfig.pdfPage")
        pdf_dpi = _positive_int_config(reference_config.get("pdfDpi", 144), "referenceConfig.pdfDpi")
        output_name = _safe_template_asset_name(reference_config.get("outputName") or "reference.png", default="reference.png")

        rendered = self._render_pdf_from_object(source_pdf, workdir, pdf_page=pdf_page, pdf_dpi=pdf_dpi)
        destination = workdir / output_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), rendered):
            raise ValueError(f"unable to write generated reference image: {destination}")
        return {"reference": output_name, "2d": True, "goodMatchPercent": 0.25, "maxFeatures": 2000}

    def _render_pdf_from_object(self, osskey: str, workdir: Path, *, pdf_page: int, pdf_dpi: int) -> np.ndarray:
        import fitz

        source_path = workdir / "_generated_template_assets" / _safe_component(Path(osskey).name or "template.pdf")
        self.object_storage.download_file(osskey, source_path)
        try:
            doc = fitz.open(str(source_path))
            try:
                if pdf_page < 1 or pdf_page > len(doc):
                    raise ValueError(f"PDF page {pdf_page} out of range for generated template asset '{osskey}' (has {len(doc)} pages)")
                page = doc[pdf_page - 1]
                mat = fitz.Matrix(pdf_dpi / 72, pdf_dpi / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
                return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"unable to render generated template asset PDF '{osskey}': {exc}") from exc

    def _sheet_workdir(self, task_id: str, sheet_id: str) -> Path:
        workdir = self.config.storage.service_data_dir / "tasks" / _safe_component(task_id) / "sheets" / _safe_component(sheet_id)
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir

    def _compute_batch_status(self, task_id: str, *, artifact_errors: bool) -> str:
        sheets = self.store.list_sheets(task_id)
        completed = sum(1 for sheet in sheets if sheet["status"] == "completed")
        failed = sum(1 for sheet in sheets if sheet["status"] == "failed")
        if failed == 0 and not artifact_errors:
            return "completed"
        if completed == 0:
            return "failed"
        return "partial_failed"

    def _result_from_store(self, task_id: str, *, status: str | None = None) -> BatchRecognitionResult:
        batch = self._require_batch(task_id)
        sheets = self.store.list_sheets(task_id)
        sheet_results = []
        for sheet in sheets:
            artifacts = [
                ArtifactPayload(
                    artifact_type=artifact["artifact_type"],
                    osskey=artifact["osskey"],
                    metadata=artifact.get("metadata_json"),
                )
                for artifact in self.store.list_artifacts(task_id, sheet_id=sheet["sheet_id"])
            ]
            sheet_results.append(
                SheetRecognitionResult(
                    sheet_id=sheet["sheet_id"],
                    source_osskey=sheet["source_osskey"],
                    status=sheet["status"],
                    result=sheet.get("result_json") or {},
                    artifacts=artifacts,
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


def _is_local_template_reference(reference_path: Path) -> bool:
    return not reference_path.is_absolute() and len(reference_path.parts) == 1


def _safe_reference_filename(reference: str, *, index: int) -> str:
    suffix = Path(reference).suffix
    if not suffix or len(suffix) > 16 or _SAFE_COMPONENT_PATTERN.search(suffix.lstrip(".")):
        suffix = ".png"
    stem = _safe_component(Path(reference).stem or f"reference-{index + 1}")
    return f"reference-{index + 1}-{stem}{suffix}"


def _safe_config_dependency_dir(*parts: str) -> Path:
    config_root = Path("config")
    dependency_dir = config_root.joinpath(*parts)
    resolved_config_root = config_root.resolve(strict=False)
    resolved_dependency_dir = dependency_dir.resolve(strict=False)
    if resolved_config_root != resolved_dependency_dir and resolved_config_root not in resolved_dependency_dir.parents:
        raise ValueError(f"template dependency directory is outside config directory: {dependency_dir}")
    return dependency_dir


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _runtime_archive_regions(recognition_config: dict) -> list[dict] | None:
    raw_regions = recognition_config.get("regions")
    if raw_regions is None:
        return None
    if isinstance(raw_regions, dict):
        raw_regions = raw_regions.get("archiveRegions")
    if not isinstance(raw_regions, list):
        return None
    return [_normalize_archive_region(region) for region in raw_regions if isinstance(region, dict)]


def _normalize_archive_region(region: dict) -> dict:
    normalized = dict(region)
    normalized["regionCode"] = str(region.get("regionCode", "")).strip()
    normalized["regionName"] = str(region.get("regionName", "")).strip()
    normalized["type"] = str(region.get("type", "")).strip()
    normalized["bbox"] = [_normalize_region_coordinate(value) for value in region.get("bbox", [])]
    return normalized


def _normalize_region_coordinate(value) -> int | float:
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _merge_json_file(path: Path, override: dict) -> dict:
    if not path.exists():
        return override
    try:
        base = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return override
    if not isinstance(base, dict):
        return override
    return _deep_merge_dicts(base, override)


def _deep_merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(base_value, value)
        else:
            merged[key] = value
    return merged


def _ensure_template_preprocessors(template: dict, generated_pre_processors: list[dict]) -> dict:
    rewritten = dict(template)
    existing = rewritten.get("preProcessors")
    pre_processors = list(existing) if isinstance(existing, list) else []
    for generated in reversed(generated_pre_processors):
        name = generated.get("name")
        existing_index = next(
            (index for index, item in enumerate(pre_processors) if isinstance(item, dict) and item.get("name") == name),
            None,
        )
        if existing_index is not None:
            pre_processors[existing_index] = _deep_merge_dicts(pre_processors[existing_index], generated)
            continue
        pre_processors.insert(0, generated)
    rewritten["preProcessors"] = pre_processors
    return rewritten


def _required_config_string(config: dict, key: str, display_name: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{display_name} must be a non-empty string")
    return value.strip()


def _positive_int_config(value, display_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{display_name} must be a positive integer")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{display_name} must be a positive integer")
    return value


def _bbox_config(value, display_name: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{display_name} must be a list of four numbers")
    bbox = []
    for index, coordinate in enumerate(value):
        if isinstance(coordinate, bool) or not isinstance(coordinate, int | float):
            raise ValueError(f"{display_name}[{index}] must be a number")
        bbox.append(int(round(float(coordinate))))
    if bbox[2] <= 0 or bbox[3] <= 0:
        raise ValueError(f"{display_name} width and height must be positive")
    return bbox


def _clamped_bbox(bbox: list[int], page_width: int, page_height: int, display_name: str) -> tuple[int, int, int, int]:
    x, y, width, height = bbox
    if x >= page_width or y >= page_height or x + width <= 0 or y + height <= 0:
        raise ValueError(f"{display_name} is outside generated reference page bounds")
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(page_width, x + width)
    y1 = min(page_height, y + height)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"{display_name} has no area inside generated reference page bounds")
    return x0, y0, x1 - x0, y1 - y0


def _safe_template_asset_name(value, *, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        value = default
    name = _safe_component(Path(value).name)
    suffix = Path(name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        name = f"{Path(name).stem or Path(default).stem}.png"
    return name


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


def _ensure_within_directory(path: Path, directory: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_directory = directory.resolve(strict=False)
    if resolved_path != resolved_directory and resolved_directory not in resolved_path.parents:
        raise ValueError(f"artifact localPath is outside region artifact directory: {path}")
