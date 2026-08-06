from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from src.services.batch_models import BatchRecognitionRequest, BatchSheetRequest
from src.services.batch_models import ArtifactPayload
from src.services.cos_client import LocalCosClient
from src.services.service_config import ArchiveRegionConfig, CallbackConfig, RecognitionConfig, ServiceConfig, StorageConfig
from src.services.task_store import TaskStore
from src.services.batch_service import BatchRecognitionService, RecognitionOutput


def _make_store(tmp_path: Path) -> TaskStore:
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    return store


def _make_config(
    tmp_path: Path,
    *,
    regions: list[ArchiveRegionConfig] | None = None,
    template_dir: Path | None = None,
    debug_artifacts: bool = False,
    callback_url: str | None = None,
) -> ServiceConfig:
    return ServiceConfig(
        storage=StorageConfig(
            service_data_dir=tmp_path / "service_data",
            template_dir=template_dir or (tmp_path / "templates"),
        ),
        callback=CallbackConfig(url=callback_url),
        recognition=RecognitionConfig(debug_artifacts=debug_artifacts),
        archive_regions=regions or [],
    )


def _make_request(*, sheets: list[BatchSheetRequest] | None = None) -> BatchRecognitionRequest:
    return BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url="https://callback.example.test/omr",
        recognition_config={},
        sheets=sheets or [BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )


def _make_request_without_callback() -> BatchRecognitionRequest:
    return BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url=None,
        recognition_config={},
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )


def _make_request_with_runtime_template() -> BatchRecognitionRequest:
    return BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url="https://callback.example.test/omr",
        recognition_config={
            "template": {
                "pageDimensions": [2480, 3508],
                "fieldBlocks": {"student_id": {"fieldType": "QTYPE_INT"}},
            },
            "config": {
                "dimensions": {"display_height": 3508, "display_width": 2480},
                "outputs": {"show_image_level": 0},
            },
            "debugArtifacts": True,
        },
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )


def _make_request_with_java_style_runtime_config() -> BatchRecognitionRequest:
    return BatchRecognitionRequest(
        exam_id="17",
        external_batch_id="scan_batch_file:1785991732373",
        callback_url=None,
        recognition_config={
            "templateConfig": {"fieldBlocks": {"student_id": {"fieldType": "QTYPE_INT"}}},
            "config": {
                "dimensions": {
                    "displayHeight": 1682,
                    "displayWidth": 1190,
                    "processingHeight": 1682,
                    "processingWidth": 1190,
                },
                "outputs": {
                    "showImageLevel": 0,
                    "saveImageLevel": 0,
                    "saveDetections": True,
                },
                "thresholdParams": {
                    "gammaLow": 0.7,
                    "minGap": 30,
                    "minJump": 25,
                    "confidentSurplus": 5,
                    "jumpDelta": 30,
                    "pageTypeForThreshold": "white",
                },
                "alignmentParams": {"autoAlign": False},
                "pdfParams": {"pdfDpi": 144, "pdfPage": 1},
                "weakMarkParams": {
                    "enabled": True,
                    "minGap": 10,
                    "maxMean": 215,
                    "supportedFieldTypes": ["QTYPE_MCQ4"],
                    "excludeLabels": [],
                },
                "weakIdentifierParams": {
                    "enabled": True,
                    "labels": [],
                    "excludeLabels": [],
                    "minGap": 20,
                    "minDeltaFromBlank": 25,
                    "maxMean": 205,
                    "supportedFieldTypes": ["QTYPE_INT"],
                },
                "weakMultiMarkParams": {
                    "enabled": True,
                    "labels": [],
                    "onlyWhenBlank": True,
                    "minDeltaFromBlank": 10,
                    "maxMean": 218,
                    "maxMarks": 4,
                    "fullSelectFallbackEnabled": True,
                    "fullSelectMaxMean": 170,
                    "fullSelectMinDeltaFromBlank": 35,
                    "fullSelectMaxSpread": 25,
                },
            },
        },
        sheets=[BatchSheetRequest(sheet_id="1", osskey="incoming/sheet-1.png")],
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
                "osskey": "incoming/sheet-1.png",
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
        config=_make_config(tmp_path, regions=regions, debug_artifacts=True),
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


def test_process_batch_writes_request_template_and_config_before_recognition(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "template.json").write_text(json.dumps({"pageDimensions": [1, 1]}), encoding="utf-8")
    (template_dir / "config.json").write_text(json.dumps({"outputs": {"show_image_level": 1}}), encoding="utf-8")

    def fake_runner(context):
        assert json.loads((context.workdir / "template.json").read_text(encoding="utf-8")) == context.request.recognition_config[
            "template"
        ]
        assert json.loads((context.workdir / "config.json").read_text(encoding="utf-8")) == context.request.recognition_config[
            "config"
        ]
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, template_dir=template_dir),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request_with_runtime_template())

    result = service.process_batch("task-1")

    assert result.status == "completed"


def test_process_batch_accepts_template_config_alias(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url="https://callback.example.test/omr",
        recognition_config={"templateConfig": {"fieldBlocks": {"student_id": {"fieldType": "QTYPE_INT"}}}, "config": {}},
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )

    def fake_runner(context):
        assert json.loads((context.workdir / "template.json").read_text(encoding="utf-8")) == request.recognition_config[
            "templateConfig"
        ]
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(request)

    assert service.process_batch("task-1").status == "completed"


def test_process_batch_normalizes_java_style_runtime_config(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")

    def fake_runner(context):
        runtime_config = json.loads((context.workdir / "config.json").read_text(encoding="utf-8"))
        assert runtime_config["dimensions"] == {
            "display_height": 1682,
            "display_width": 1190,
            "processing_height": 1682,
            "processing_width": 1190,
        }
        assert runtime_config["outputs"] == {
            "show_image_level": 0,
            "save_image_level": 0,
            "save_detections": True,
        }
        assert runtime_config["threshold_params"]["GAMMA_LOW"] == 0.7
        assert runtime_config["alignment_params"] == {"auto_align": False}
        assert runtime_config["pdf_params"] == {"pdf_dpi": 144, "pdf_page": 1}
        assert runtime_config["weak_mark_params"]["supported_field_types"] == ["QTYPE_MCQ4"]
        assert runtime_config["weak_identifier_params"]["min_delta_from_blank"] == 25
        assert runtime_config["weak_multi_mark_params"]["full_select_fallback_enabled"] is True
        assert "thresholdParams" not in runtime_config
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request_with_java_style_runtime_config())

    assert service.process_batch("task-1").status == "completed"


def test_fake_cos_smoke_terminal_payload_contains_business_artifact_fields(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    regions = [ArchiveRegionConfig(region_code="exam_no", region_name="准考证号区域", type="student_id", bbox=[5, 10, 40, 20])]

    def fake_runner(context):
        checked_path = context.workdir / "checked" / "sheet-1.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"answers": {"q1": "A"}}, checked_image_path=checked_path)

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, regions=regions),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    payload = service.process_batch("task-1").to_callback_dict()

    sheet = payload["sheets"][0]
    assert payload["examId"] == "exam-1"
    assert sheet["sheetId"] == "sheet-1"
    assert sheet["osskey"] == "incoming/sheet-1.png"
    assert sheet["answers"] == {"q1": "A"}
    assert sheet["regionImages"][0]["osskey"] == "artifacts/task-1/sheet-1/001_sheet-1_exam_no_准考证号区域.png"
    assert sheet["checkedImageOsskey"] == "checked/task-1/sheet-1/sheet-1.png"
    assert (tmp_path / "cos" / "checked" / "task-1" / "sheet-1" / "sheet-1.png").is_file()


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
            if str(osskey).startswith("artifacts/"):
                raise RuntimeError("upload denied")
            return super().upload_file(local_path, osskey, content_type=content_type)

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
        config=_make_config(tmp_path, regions=regions, debug_artifacts=True),
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


def test_checked_image_upload_failure_is_non_fatal_and_reflected_in_result_metadata(tmp_path: Path) -> None:
    class CheckedUploadFailingCos(LocalCosClient):
        def upload_file(self, local_path, osskey, content_type=None):
            if str(osskey).startswith("checked/"):
                raise RuntimeError("checked upload denied")
            return super().upload_file(local_path, osskey, content_type=content_type)

    store = _make_store(tmp_path)
    source_cos = tmp_path / "cos"
    _write_image(source_cos / "incoming" / "sheet-1.png")

    def fake_runner(context):
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"score": 98}, checked_image_path=checked_path)

    service = BatchRecognitionService(
        store=store,
        object_storage=CheckedUploadFailingCos(source_cos),
        config=_make_config(tmp_path),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    result = service.process_batch("task-1")

    assert result.status == "partial_failed"
    sheet = store.list_sheets("task-1")[0]
    assert sheet["status"] == "completed"
    assert sheet["result_json"]["artifactErrors"] == [
        {
            "artifactType": "checked_image",
            "localPath": sheet["result_json"]["artifactErrors"][0]["localPath"],
            "osskey": "checked/task-1/sheet-1/checked.png",
            "error": "checked upload denied",
        }
    ]


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
        config=_make_config(tmp_path, template_dir=template_dir, debug_artifacts=True),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    service.process_batch("task-1")

    assert copied_paths["reference"].is_file()
    assert copied_paths["config"].read_text(encoding="utf-8") == '{"dimensions": {}}'
    assert copied_paths["template"].read_text(encoding="utf-8") == '{"fields": []}'


def test_process_batch_uses_injected_region_artifact_generator(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    generator_calls = []

    def fake_runner(context):
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"score": 88}, checked_image_path=checked_path)

    def fake_region_generator(image_path, regions, output_dir, *, sheet_id=None, task_id=None):
        generator_calls.append((image_path, list(regions), output_dir, sheet_id, task_id))
        local_path = output_dir / "fake.png"
        _write_image(local_path)
        return [
            ArtifactPayload(
                artifact_type="region_screenshot",
                osskey=str(local_path),
                metadata={"localPath": str(local_path), "regionName": "fake"},
            )
        ]

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, regions=[ArchiveRegionConfig(region_code="r", region_name="区域", type="type", bbox=[1, 1, 2, 2])]),
        recognition_runner=fake_runner,
        region_artifact_generator=fake_region_generator,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    service.process_batch("task-1")

    assert len(generator_calls) == 1
    assert generator_calls[0][3:] == ("sheet-1", "task-1")
    assert store.list_artifacts("task-1", sheet_id="sheet-1")[0]["osskey"] == "artifacts/task-1/sheet-1/fake.png"


def test_process_batch_invokes_callback_client_and_records_attempt(tmp_path: Path) -> None:
    class RecordingCallbackClient:
        def __init__(self):
            self.payloads = []

        def send(self, payload):
            self.payloads.append(payload)
            return {"status_code": 202, "response_text": "accepted", "success": True}

    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    callback_client = RecordingCallbackClient()
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=lambda context: RecognitionOutput(result={"ok": True}),
        callback_client=callback_client,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    service.process_batch("task-1")

    assert callback_client.payloads[0]["taskId"] == "task-1"
    assert callback_client.payloads[0]["status"] == "completed"
    attempts = store.list_callback_attempts("task-1")
    assert attempts[0]["target_url"] == "https://callback.example.test/omr"
    assert attempts[0]["status_code"] == 202
    assert attempts[0]["success"] is True
    assert attempts[0]["request_json"] == callback_client.payloads[0]


def test_process_batch_uses_config_callback_url_when_request_omits_it(tmp_path: Path) -> None:
    class RecordingCallbackClient:
        def __init__(self):
            self.payloads = []

        def send(self, payload):
            self.payloads.append(payload)
            return {"status_code": 200, "response_text": "ok", "success": True}

    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    callback_client = RecordingCallbackClient()
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, callback_url="https://config.example.test/omr-callback"),
        recognition_runner=lambda context: RecognitionOutput(result={"ok": True}),
        callback_client=callback_client,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request_without_callback())

    service.process_batch("task-1")

    assert callback_client.payloads[0]["taskId"] == "task-1"
    assert store.get_batch("task-1")["callback_url"] == "https://config.example.test/omr-callback"
    assert store.list_callback_attempts("task-1")[0]["target_url"] == "https://config.example.test/omr-callback"


def test_process_batch_sanitizes_sheet_id_for_workdir_and_artifact_key(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    observed_workdirs = []

    def fake_runner(context):
        observed_workdirs.append(context.workdir)
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"ok": True}, checked_image_path=checked_path)

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(
            tmp_path,
            regions=[ArchiveRegionConfig(region_code="r", region_name="区域", type="type", bbox=[5, 10, 40, 20])],
        ),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task/../1",
    )
    service.submit_batch(_make_request(sheets=[BatchSheetRequest(sheet_id="../evil sheet", osskey="incoming/sheet-1.png")]))

    service.process_batch("task/../1")

    expected_root = tmp_path / "service_data" / "tasks" / "task_1" / "sheets" / "evil_sheet"
    assert observed_workdirs == [expected_root]
    artifact = store.list_artifacts("task/../1", sheet_id="../evil sheet")[0]
    assert artifact["osskey"].startswith("artifacts/task_1/evil_sheet/")
    assert not (tmp_path / "service_data" / "tasks" / "evil sheet").exists()


def test_template_dependency_copying_skips_symlinks(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    template_dir = tmp_path / "templates"
    template_dir.mkdir(parents=True)
    secret = tmp_path / "secret.txt"
    secret.write_text("do not copy", encoding="utf-8")
    (template_dir / "reference.png").symlink_to(secret)
    copied_workdirs = []

    def fake_runner(context):
        copied_workdirs.append(context.workdir)
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

    assert not (copied_workdirs[0] / "reference.png").exists()


def test_region_generator_local_path_must_stay_under_region_output_dir(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    outside = tmp_path / "outside.png"
    _write_image(outside)

    def fake_runner(context):
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"ok": True}, checked_image_path=checked_path)

    def malicious_generator(image_path, regions, output_dir, *, sheet_id=None, task_id=None):
        return [ArtifactPayload(artifact_type="region_screenshot", osskey=str(outside), metadata={"localPath": str(outside)})]

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, regions=[ArchiveRegionConfig(region_code="r", region_name="区域", type="type", bbox=[1, 1, 2, 2])]),
        recognition_runner=fake_runner,
        region_artifact_generator=malicious_generator,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    result = service.process_batch("task-1")

    assert result.status == "partial_failed"
    sheet = store.list_sheets("task-1")[0]
    assert "outside region artifact directory" in sheet["result_json"]["artifactErrors"][0]["error"]
    assert store.list_artifacts("task-1") == []


def test_callback_exception_is_recorded_without_failing_batch(tmp_path: Path) -> None:
    class FailingCallbackClient:
        def send(self, payload):
            raise RuntimeError("callback down")

    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=lambda context: RecognitionOutput(result={"ok": True}),
        callback_client=FailingCallbackClient(),
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(_make_request())

    result = service.process_batch("task-1")

    assert result.status == "completed"
    attempt = store.list_callback_attempts("task-1")[0]
    assert attempt["success"] is False
    assert attempt["error"] == "callback down"


def _runner_that_writes_process_files(context):
    context.workdir.mkdir(parents=True, exist_ok=True)
    source_dir = context.workdir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    output_dir = context.workdir / "output" / "CheckedOMRs"
    output_dir.mkdir(parents=True, exist_ok=True)
    checked_image = output_dir / f"{context.sheet.sheet_id}.png"
    _write_image(checked_image)
    process_file = context.workdir / "output" / "process-debug.txt"
    process_file.write_text("debug", encoding="utf-8")
    return RecognitionOutput(
        result={"answers": {"Q1": "A"}, "checkedImagePath": str(checked_image)},
        checked_image_path=checked_image,
    )


def test_process_batch_cleans_sheet_workdirs_by_default(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=_runner_that_writes_process_files,
        task_id_factory=lambda: "task-1",
    )
    submitted = service.submit_batch(_make_request())

    result = service.process_batch(submitted.task_id)

    assert result.status == "completed"
    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert not sheet_workdir.exists()
    assert result.sheets[0].result["checkedImageOsskey"].startswith("checked/")


def test_process_batch_preserves_sheet_workdirs_when_request_debug_artifacts_true(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=_runner_that_writes_process_files,
        task_id_factory=lambda: "task-1",
    )
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "externalBatchId": "external-batch-1",
            "callbackUrl": "https://callback.example.test/omr",
            "recognitionConfig": {"debugArtifacts": True},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )
    submitted = service.submit_batch(request)

    result = service.process_batch(submitted.task_id)

    assert result.status == "completed"
    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert (sheet_workdir / "output" / "process-debug.txt").exists()


def test_process_batch_request_false_cleans_when_service_config_preserves(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, debug_artifacts=True),
        recognition_runner=_runner_that_writes_process_files,
        task_id_factory=lambda: "task-1",
    )
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "externalBatchId": "external-batch-1",
            "callbackUrl": "https://callback.example.test/omr",
            "recognitionConfig": {"debugArtifacts": False},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )
    submitted = service.submit_batch(request)

    service.process_batch(submitted.task_id)

    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert not sheet_workdir.exists()
