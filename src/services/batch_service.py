from __future__ import annotations

import shutil
import uuid
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
from .region_artifacts import generate_region_artifacts
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
        self.store.create_batch(
            task_id=task_id,
            exam_id=request.exam_id,
            external_batch_id=request.external_batch_id,
            status="pending",
            callback_url=request.callback_url,
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
        self.store.update_batch_status(task_id, "running")

        any_artifact_errors = False
        for sheet_request in request.sheets:
            self.store.update_sheet(
                task_id=task_id,
                sheet_id=sheet_request.sheet_id,
                source_osskey=sheet_request.osskey,
                status="running",
                result_json={},
            )
            workdir = self._sheet_workdir(task_id, sheet_request.sheet_id)
            try:
                source_path = workdir / "source" / Path(sheet_request.osskey).name
                self.object_storage.download_file(sheet_request.osskey, source_path)
                self._copy_template_dependencies(workdir)
                output = self.recognition_runner(
                    RecognitionContext(
                        task_id=task_id,
                        sheet=sheet_request,
                        source_path=source_path,
                        workdir=workdir,
                        request=request,
                    )
                )
                result_json = output.result
                if isinstance(result_json, dict):
                    stored_result = dict(result_json)
                else:
                    stored_result = result_json

                artifact_errors = []
                if output.checked_image_path is not None and self.config.archive_regions:
                    local_artifacts = self.region_artifact_generator(
                        output.checked_image_path,
                        self.config.archive_regions,
                        workdir / "region_artifacts",
                        sheet_id=sheet_request.sheet_id,
                        task_id=task_id,
                    )
                    uploaded, artifact_errors = self._upload_region_artifacts(
                        task_id,
                        sheet_request.sheet_id,
                        local_artifacts,
                        workdir / "region_artifacts",
                    )
                    if isinstance(stored_result, dict) and artifact_errors:
                        stored_result["artifactErrors"] = artifact_errors
                    if artifact_errors:
                        any_artifact_errors = True

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
        final_result = self._result_from_store(task_id)
        self._send_callback_if_configured(batch, final_result)
        return final_result

    def _send_callback_if_configured(self, batch: dict, result: BatchRecognitionResult) -> None:
        if self.callback_client is None or not batch.get("callback_url"):
            return

        payload = result.to_callback_dict()
        try:
            response = self.callback_client.send(payload)
            response_data = response if isinstance(response, dict) else {}
            self.store.add_callback_attempt(
                task_id=result.task_id,
                target_url=batch["callback_url"],
                status_code=response_data.get("status_code"),
                success=bool(response_data.get("success", True)),
                error=response_data.get("error"),
                request_json=payload,
                response_text=response_data.get("response_text"),
            )
        except Exception as exc:  # noqa: BLE001 - callback failure must be recorded, not raised.
            self.store.add_callback_attempt(
                task_id=result.task_id,
                target_url=batch["callback_url"],
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

    def _copy_template_dependencies(self, workdir: Path) -> None:
        template_dir = self.config.storage.template_dir
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
                shutil.copy2(source, workdir / source.name)

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


def _ensure_within_directory(path: Path, directory: Path) -> None:
    resolved_path = path.resolve(strict=False)
    resolved_directory = directory.resolve(strict=False)
    if resolved_path != resolved_directory and resolved_directory not in resolved_path.parents:
        raise ValueError(f"artifact localPath is outside region artifact directory: {path}")
