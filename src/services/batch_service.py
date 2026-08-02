from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

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
                    local_artifacts = generate_region_artifacts(
                        output.checked_image_path,
                        self.config.archive_regions,
                        workdir / "region_artifacts",
                        sheet_id=sheet_request.sheet_id,
                        task_id=task_id,
                    )
                    uploaded, artifact_errors = self._upload_region_artifacts(task_id, sheet_request.sheet_id, local_artifacts)
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
        return self._result_from_store(task_id)

    def _upload_region_artifacts(
        self,
        task_id: str,
        sheet_id: str,
        local_artifacts: list[ArtifactPayload],
    ) -> tuple[list[ArtifactPayload], list[dict]]:
        uploaded: list[ArtifactPayload] = []
        errors: list[dict] = []
        for artifact in local_artifacts:
            metadata = dict(artifact.metadata or {})
            local_path = Path(str(metadata.get("localPath", artifact.osskey)))
            remote_key = f"artifacts/{task_id}/{sheet_id}/{local_path.name}"
            try:
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
        for source in template_dir.iterdir():
            if source.is_file():
                shutil.copy2(source, workdir / source.name)

    def _sheet_workdir(self, task_id: str, sheet_id: str) -> Path:
        workdir = self.config.storage.service_data_dir / "tasks" / task_id / "sheets" / sheet_id
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
