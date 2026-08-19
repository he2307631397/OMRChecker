from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from src.services.batch_models import BatchRecognitionRequest, BatchSheetRequest
from src.services.cos_client import LocalCosClient
from src.services.service_config import CallbackConfig, RecognitionConfig, ServiceConfig, StorageConfig
from src.services.task_store import TaskStore
from src.services.batch_service import BatchRecognitionService, RecognitionOutput


def _make_store(tmp_path: Path) -> TaskStore:
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    return store


def _make_config(
    tmp_path: Path,
    *,
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


def test_process_batch_downloads_runs_recognition_and_marks_completed_without_screenshot_archiving(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    runner_calls = []

    def fake_runner(context):
        runner_calls.append(context)
        checked_path = context.workdir / "checked" / f"{context.sheet.sheet_id}.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"score": 98})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, debug_artifacts=True),
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
    assert callback["sheets"][0]["artifacts"] == []
    assert not (tmp_path / "cos" / "artifacts").exists()
    assert not (tmp_path / "cos" / "checked").exists()
    assert store.get_batch("task-1")["status"] == "completed"
    assert store.get_batch("task-1")["completed_at"] is not None
    assert store.list_sheets("task-1")[0]["status"] == "completed"
    assert store.list_artifacts("task-1", sheet_id="sheet-1") == []


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


def test_process_batch_ignores_empty_template_config_alias(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "template.json").write_text('{"pageDimensions": [1, 1]}', encoding="utf-8")
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        callback_url=None,
        recognition_config={"templateConfig": {"bubbleDimensions": None, "fieldBlocks": None, "pageDimensions": None}},
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )

    def fake_runner(context):
        assert json.loads((context.workdir / "template.json").read_text(encoding="utf-8")) == {"pageDimensions": [1, 1]}
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, template_dir=template_dir),
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


def test_process_batch_coerces_java_numeric_runtime_config(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    request = _make_request_with_java_style_runtime_config()
    request.recognition_config["config"]["dimensions"] = {
        "display_height": 1682.0,
        "display_width": 1190.0,
        "processing_height": 1682.0,
        "processing_width": 1190.0,
    }
    request.recognition_config["config"]["weakMultiMarkParams"]["excludeLabels"] = None

    def fake_runner(context):
        runtime_config = json.loads((context.workdir / "config.json").read_text(encoding="utf-8"))
        assert runtime_config["dimensions"] == {
            "display_height": 1682,
            "display_width": 1190,
            "processing_height": 1682,
            "processing_width": 1190,
        }
        assert "exclude_labels" not in runtime_config["weak_multi_mark_params"]
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


def test_process_batch_uses_template_code_schema_version_dependency_dir(monkeypatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    config_v1 = (tmp_path / "config" / "ASTS-HTTP-001" / "v1").resolve(strict=False)
    config_v1.mkdir(parents=True)
    (config_v1 / "reference.png").write_bytes(b"versioned-reference")
    (config_v1 / "evaluation.json").write_text("{}\n", encoding="utf-8")
    default_template_dir = tmp_path / "templates"
    default_template_dir.mkdir()
    (default_template_dir / "reference.png").write_bytes(b"default-reference")
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        external_batch_id="external-batch-1",
        callback_url="https://callback.example.test/omr",
        template_code="ASTS-HTTP-001",
        schema_version="v1",
        recognition_config={"templateConfig": {"preProcessors": [{"options": {"reference": "reference.png"}}]}},
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )

    monkeypatch.chdir(tmp_path)

    def fake_runner(context):
        assert context.template_dir == config_v1
        assert (context.workdir / "reference.png").read_bytes() == b"versioned-reference"
        assert not (context.workdir / "evaluation.json").exists()
        assert not (context.workdir / "template.json").exists()
        assert json.loads((config_v1 / "template.json").read_text(encoding="utf-8")) == request.recognition_config[
            "templateConfig"
        ]
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path, template_dir=default_template_dir),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(request)

    assert service.process_batch("task-1").status == "completed"


def test_process_batch_persists_runtime_jsons_to_template_code_schema_dir(monkeypatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    config_v1 = (tmp_path / "config" / "ASTS-HTTP-001" / "v1").resolve(strict=False)
    config_v1.mkdir(parents=True)
    (config_v1 / "reference.png").write_bytes(b"reference")
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        callback_url=None,
        template_code="ASTS-HTTP-001",
        schema_version="v1",
        recognition_config={
            "templateConfig": {"pageDimensions": [1190, 1682], "bubbleDimensions": None},
            "config": {"dimensions": {"display_height": 1682.0, "display_width": 1190.0}},
        },
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )
    monkeypatch.chdir(tmp_path)

    def fake_runner(context):
        assert context.template_dir == config_v1
        assert (config_v1 / "template.json").is_file()
        assert (config_v1 / "config.json").is_file()
        assert not (context.workdir / "template.json").exists()
        assert not (context.workdir / "config.json").exists()
        assert (context.workdir / "reference.png").read_bytes() == b"reference"
        runtime_config = json.loads((config_v1 / "config.json").read_text(encoding="utf-8"))
        assert runtime_config["dimensions"] == {"display_height": 1682, "display_width": 1190}
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


def test_process_batch_downloads_template_preprocessor_reference_oss_key(monkeypatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    (tmp_path / "cos" / "template-assets").mkdir(parents=True)
    (tmp_path / "cos" / "template-assets" / "remote-reference.png").write_bytes(b"remote-reference")
    config_v1 = (tmp_path / "config" / "ASTS-HTTP-001" / "v1").resolve(strict=False)
    config_v1.mkdir(parents=True)
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        callback_url=None,
        template_code="ASTS-HTTP-001",
        schema_version="v1",
        recognition_config={
            "templateConfig": {
                "pageDimensions": [1190, 1682],
                "preProcessors": [
                    {
                        "name": "FeatureBasedAlignment",
                        "options": {
                            "reference": "template-assets/remote-reference.png",
                            "2d": True,
                        },
                    }
                ],
            }
        },
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )
    monkeypatch.chdir(tmp_path)

    def fake_runner(context):
        written_template = json.loads((config_v1 / "template.json").read_text(encoding="utf-8"))
        pre_processor = written_template["preProcessors"][0]
        assert pre_processor["options"]["reference"] == "remote-reference.png"
        assert pre_processor["options"]["2d"] is True
        assert (config_v1 / "remote-reference.png").read_bytes() == b"remote-reference"
        assert (context.workdir / "remote-reference.png").read_bytes() == b"remote-reference"
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


def test_process_batch_reuses_downloaded_template_preprocessor_reference(monkeypatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    (tmp_path / "cos" / "template-assets").mkdir(parents=True)
    (tmp_path / "cos" / "template-assets" / "shared-reference.png").write_bytes(b"shared-reference")
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        callback_url=None,
        recognition_config={
            "templateConfig": {
                "preProcessors": [
                    {"name": "FeatureBasedAlignment", "options": {"reference": "template-assets/shared-reference.png"}},
                    {"name": "FeatureBasedAlignment", "options": {"reference": "template-assets/shared-reference.png"}},
                ]
            },
            "debugArtifacts": True,
        },
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )
    monkeypatch.chdir(tmp_path)

    def fake_runner(context):
        written_template = json.loads((context.workdir / "template.json").read_text(encoding="utf-8"))
        references = [item["options"]["reference"] for item in written_template["preProcessors"]]
        assert references == ["shared-reference.png", "shared-reference.png"]
        assert (context.workdir / "shared-reference.png").read_bytes() == b"shared-reference"
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


def test_process_batch_requires_central_template_json_for_template_code(monkeypatch, tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    (tmp_path / "config" / "ASTS-HTTP-001" / "v1").mkdir(parents=True)
    request = BatchRecognitionRequest(
        exam_id="exam-1",
        callback_url=None,
        template_code="ASTS-HTTP-001",
        schema_version="v1",
        recognition_config={"templateConfig": {"bubbleDimensions": None, "fieldBlocks": None}},
        sheets=[BatchSheetRequest(sheet_id="sheet-1", osskey="incoming/sheet-1.png")],
    )
    monkeypatch.chdir(tmp_path)
    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=lambda _context: RecognitionOutput(result={"ok": True}),
        task_id_factory=lambda: "task-1",
    )
    service.submit_batch(request)

    with pytest.raises(ValueError, match="template.json is required"):
        service.process_batch("task-1")


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


def test_process_batch_sanitizes_sheet_id_for_workdir(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    cos = LocalCosClient(tmp_path / "cos")
    _write_image(tmp_path / "cos" / "incoming" / "sheet-1.png")
    observed_workdirs = []

    def fake_runner(context):
        observed_workdirs.append(context.workdir)
        checked_path = context.workdir / "checked.png"
        _write_image(checked_path)
        return RecognitionOutput(result={"ok": True})

    service = BatchRecognitionService(
        store=store,
        object_storage=cos,
        config=_make_config(tmp_path),
        recognition_runner=fake_runner,
        task_id_factory=lambda: "task/../1",
    )
    service.submit_batch(_make_request(sheets=[BatchSheetRequest(sheet_id="../evil sheet", osskey="incoming/sheet-1.png")]))

    service.process_batch("task/../1")

    expected_root = tmp_path / "service_data" / "tasks" / "task_1" / "sheets" / "evil_sheet"
    assert observed_workdirs == [expected_root]
    assert store.list_artifacts("task/../1", sheet_id="../evil sheet") == []
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
    return RecognitionOutput(result={"answers": {"Q1": "A"}})


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
    assert "checkedImageOsskey" not in result.sheets[0].result
    assert "checkedImagePath" not in result.sheets[0].result


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
