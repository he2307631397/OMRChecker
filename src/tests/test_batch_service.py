from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from src.services.batch_models import BatchRecognitionRequest, BatchSheetRequest
from src.services.cos_client import LocalCosClient
from src.services.service_config import ArchiveRegionConfig, ServiceConfig, StorageConfig
from src.services.task_store import TaskStore
from src.services.batch_service import BatchRecognitionService, RecognitionOutput


def _make_store(tmp_path: Path) -> TaskStore:
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    return store


def _make_config(tmp_path: Path, *, regions: list[ArchiveRegionConfig] | None = None, template_dir: Path | None = None) -> ServiceConfig:
    return ServiceConfig(
        storage=StorageConfig(
            service_data_dir=tmp_path / "service_data",
            template_dir=template_dir or (tmp_path / "templates"),
        ),
        archive_regions=regions or [],
    )


def _make_request(*, sheets: list[BatchSheetRequest] | None = None) -> BatchRecognitionRequest:
    return BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url="https://callback.example.test/omr",
        recognition_config={"template": "default"},
        sheets=sheets or [BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    image[10:30, 5:45] = (0, 0, 255)
    assert cv2.imwrite(str(path), image)


def test_submit_batch_persists_batch_and_sheets_and_returns_business_fields(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    service = BatchRecognitionService(
        store=store,
        object_storage=LocalCosClient(tmp_path / "cos"),
        config=_make_config(tmp_path),
        task_id_factory=lambda: "task-1",
    )

    result = service.submit_batch(_make_request())

    assert result.to_callback_dict() == {
        "taskId": "task-1",
        "examId": "exam-1",
        "externalBatchId": "external-batch-1",
        "status": "pending",
        "aggregateCounts": {"total": 1, "pending": 1},
        "sheets": [
            {
                "sheetId": "sheet-1",
                "sourceOsskey": "incoming/sheet-1.png",
                "status": "pending",
                "result": {},
                "artifacts": [],
            }
        ],
    }
    batch = store.get_batch("task-1")
    assert batch["exam_id"] == "exam-1"
    assert batch["external_batch_id"] == "external-batch-1"
    assert batch["status"] == "pending"
    assert batch["request_json"] == _make_request().to_api_dict()
    assert [sheet["status"] for sheet in store.list_sheets("task-1")] == ["pending"]


def test_process_batch_downloads_runs_uploads_artifacts_and_marks_completed(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    regions = [ArchiveRegionConfig(region_code="exam_no", region_name="准考证号区域", type="student_id", bbox=[5, 10, 40, 20])]
    runner_calls = []

    def fake_runner(context):
        runner_calls.append(context)
        checked_path = context.workdir / "checked" / f"{context.sheet.sheet_id}.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"score": 98}, checked_image_path=checked_path)

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, regions=regions),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    result = service.process_batch("task-1")

    assert len(runner_calls) == 1
    assert runner_calls[0].source_path.read_bytes() == (tmp_path / "cos" / "incoming" / "sheet-1.png").read_bytes()
    callback = result.to_callback_dict()
    assert callback["status"] == "completed"
    assert callback["sheets"][0]["result"] == {"score": 98}
    assert callback["sheets"][0]["artifacts"][0]["osskey"] == "artifacts/task-1/sheet-1/001_sheet-1_exam_no_准考证号区域.png"
    assert (tmp_path / "cos" / "artifacts" / "task-1" / "sheet-1" / "001_sheet-1_exam_no_准考证号区域.png").is_file()
    assert store.get_batch("task-1")["status"] == "completed"
    assert store.get_batch("task-1")["completed_at"] is not None
    assert store.list_sheets("task-1")[0]["status"] == "completed"
    assert store.list_artifacts("task-1", sheet_id="sheet-1")[0]["osskey"] == "artifacts/task-1/sheet-1/001_sheet-1_exam_no_准考证号区域.png"


def test_one_sheet_recognition_failure_marks_sheet_failed_and_batch_partial_failed(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-2.png")

    def fake_runner(context):
        if context.sheet.sheet_id == "sheet-2":
            raise RuntimeError("unreadable sheet")
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(
        _make_request(
            sheets=[
                BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png"),
                BatchSheetRequest(sheet_id="sheet-2", osskey="incoming/sheet-2.png"),
            ]
        )
    )

    result = service.process_batch("task-1")

    assert result.status == "partial_failed"
    sheets = {sheet["sheet_id"]: sheet for sheet in store.list_sheets("task-1")}
    assert sheets["sheet-1"]["status"] == "completed"
    assert sheets["sheet-2"]["status"] == "failed"
    assert sheets["sheet-2"]["error"] == "unreadable sheet"


def test_artifact_upload_failure_is_non_fatal_and_reflected_in_result_metadata(tmp_path: Path) -> None:
    class UploadFailingCos(LocalCosClient):
        def upload_file(self, local_path, osskey, content_type=None):
            raise RuntimeError("upload denied")

    store = _make_store(tmp_path)
    source_cos = tmp_path / "cos"
    _write_image(source_cos / "incoming" / "sheet-1.png")
    regions = [ArchiveRegionConfig(region_code="exam_no", region_name="准考证号区域", type="student_id", bbox=[5, 10, 40, 20])]

    def fake_runner(context):
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"score": 98}, checked_image_path=checked_path)

    service = BatchRecognitionService(
        store=store,
        object_storage=UploadFailingCos(source_cos),
        config=_make_config(tmp_path, regions=regions),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    result = service.process_batch("task-1")

    assert result.status == "partial_failed"
    sheet = store.list_sheets("task-1")[0]
    assert sheet["status"] == "completed"
    assert sheet["error"] is None
    assert sheet["result_json"]["score"] == 98
    assert sheet["result_json"]["artifactErrors"] == [
        {
            "artifactType": "region_screenshot",
            "localPath": sheet["result_json"]["artifactErrors"][0]["localPath"],
            "osskey": "artifacts/task-1/sheet-1/001_sheet-1_exam_no_准考证号区域.png",
            "error": "upload denied",
        }
    ]
    assert Path(sheet["result_json"]["artifactErrors"][0]["localPath"]).is_file()
    assert store.list_artifacts("task-1") == []


def test_task_workdir_template_dependency_copying_includes_reference_png(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    template_dir = tmp_path / "templates"
    _write_image(template_dir / "reference.png")
    (template_dir / "config.json").write_text('{"dimensions": {}}', encoding="utf-8")
    (template_dir / "template.json").write_text('{"fields": []}', encoding="utf-8")
    copied_paths: dict[str, Path] = {}

    def fake_runner(context):
        copied_paths["reference"] = context.workdir / "reference.png"
        copied_paths["config"] = context.workdir / "config.json"
        copied_paths["template"] = context.workdir / "template.json"
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, template_dir=template_dir),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    service.process_batch("task-1")

    assert copied_paths["reference"].is_file()
    assert copied_paths["config"].read_text(encoding="utf-8") == '{"dimensions": {}}'
    assert copied_paths["template"].read_text(encoding="utf-8") == '{"fields": []}'
