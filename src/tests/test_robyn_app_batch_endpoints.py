from __future__ import annotations

from pathlib import Path

import web.robyn_app as robyn_app
from src.services.batch_models import BatchRecognitionRequest
from src.services.batch_service import BatchRecognitionService, RecognitionOutput
from src.services.cos_client import LocalCosClient
from src.services.omr_service import OmrRunResult
from src.services.service_config import DatabaseConfig, ServiceConfig, StorageConfig
from src.services.task_store import TaskStore


class DummyRequest:
    def __init__(self, json_payload=None, json_error=None, query_params=None):
        self._json_payload = json_payload
        self._json_error = json_error
        self.query_params = query_params or {}
        self.body = b"{}" if json_payload is not None or json_error is not None else None

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_payload


class InlineExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, fn, *args, **kwargs):
        self.submissions.append((fn, args, kwargs))
        return fn(*args, **kwargs)


class QueuedExecutor:
    def __init__(self):
        self.submissions = []

    def submit(self, fn, *args, **kwargs):
        self.submissions.append((fn, args, kwargs))
        return None


def _payload(exam_id="exam-1", external_batch_id="external-1", sheet_id="sheet-1"):
    return {
        "examId": exam_id,
        "externalBatchId": external_batch_id,
        "callbackUrl": "https://callback.example.test/omr",
        "recognitionConfig": {"templateConfig": {}, "config": {}},
        "sheets": [
            {
                "sheetId": sheet_id,
                "osskey": f"incoming/{sheet_id}.png",
                "metadata": {"seatNo": "A01"},
            }
        ],
    }


def _service(tmp_path: Path, *, task_id="batch-task-1", runner_calls=None):
    store = TaskStore(tmp_path / "omr_service.db")
    store.initialize()
    cos_root = tmp_path / "cos"
    (cos_root / "incoming").mkdir(parents=True)
    for sheet_id in ("sheet-1", "sheet-2", "sheet-3"):
        (cos_root / "incoming" / f"{sheet_id}.png").write_bytes(b"fake-image")

    def fake_runner(context):
        if runner_calls is not None:
            runner_calls.append(context)
        return RecognitionOutput(result={"recognized": context.sheet.sheet_id})

    service = BatchRecognitionService(
        store=store,
        object_storage=LocalCosClient(cos_root),
        config=ServiceConfig(storage=StorageConfig(service_data_dir=tmp_path / "service_data", template_dir=tmp_path / "templates")),
        recognition_runner=fake_runner,
        task_id_factory=lambda: task_id,
    )
    return service, store


def test_submit_valid_batch_returns_business_fields_persists_and_processes_inline(monkeypatch, tmp_path):
    runner_calls = []
    service, store = _service(tmp_path, runner_calls=runner_calls)
    executor = InlineExecutor()
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)
    monkeypatch.setattr(robyn_app, "_BATCH_EXECUTOR", executor)

    response = robyn_app.create_batch(DummyRequest(json_payload=_payload()))

    assert response == {"taskId": "batch-task-1", "examId": "exam-1", "status": "pending"}
    assert store.get_batch("batch-task-1")["exam_id"] == "exam-1"
    assert store.list_sheets("batch-task-1")[0]["status"] == "completed"
    assert len(executor.submissions) == 1
    assert [call.sheet.sheet_id for call in runner_calls] == ["sheet-1"]


def test_submit_valid_batch_echoes_batch_id_when_supplied(monkeypatch, tmp_path):
    service, _store = _service(tmp_path)
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)
    payload = _payload()
    payload["batchId"] = 1

    response = robyn_app.create_batch(DummyRequest(json_payload=payload))

    assert response == {"taskId": "batch-task-1", "examId": "exam-1", "status": "pending", "batchId": 1}


def test_submit_invalid_missing_fields_returns_error_400_style(monkeypatch, tmp_path):
    service, _store = _service(tmp_path)
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)

    response = robyn_app.create_batch(DummyRequest(json_payload={"examId": "exam-1"}))

    assert response["status"] == "failed"
    assert response["error"] == "sheets is required"


def test_get_batch_by_task_id_returns_camel_case_payload_and_unknown_returns_404(monkeypatch, tmp_path):
    service, _store = _service(tmp_path)
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)
    created = robyn_app.create_batch(DummyRequest(json_payload=_payload()))

    fetched = robyn_app.get_batch(created["taskId"])
    missing = robyn_app.get_batch("missing-task")

    assert fetched["taskId"] == created["taskId"]
    assert fetched["examId"] == "exam-1"
    assert fetched["externalBatchId"] == "external-1"
    assert fetched["sheets"][0]["sheetId"] == "sheet-1"
    assert fetched["sheets"][0]["sourceOsskey"] == "incoming/sheet-1.png"
    assert missing == {"status": "not_found", "taskId": "missing-task", "error": "batch not found"}


def test_query_batches_filters_by_exam_status_external_and_paginates(monkeypatch, tmp_path):
    service, _store = _service(tmp_path)
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)
    monkeypatch.setattr(robyn_app, "_BATCH_EXECUTOR", QueuedExecutor())
    robyn_app.create_batch(DummyRequest(json_payload=_payload(exam_id="exam-1", external_batch_id="ext-1", sheet_id="sheet-1")))
    monkeypatch.setattr(service, "task_id_factory", lambda: "batch-task-2")
    robyn_app.create_batch(DummyRequest(json_payload=_payload(exam_id="exam-1", external_batch_id="ext-2", sheet_id="sheet-2")))
    monkeypatch.setattr(service, "task_id_factory", lambda: "batch-task-3")
    robyn_app.create_batch(DummyRequest(json_payload=_payload(exam_id="exam-2", external_batch_id="ext-3", sheet_id="sheet-3")))

    by_exam = robyn_app.get_batches(DummyRequest(query_params={"examId": "exam-1"}))
    by_external = robyn_app.get_batches(DummyRequest(query_params={"externalBatchId": "ext-3"}))
    paged = robyn_app.get_batches(DummyRequest(query_params={"status": "pending", "limit": "1", "offset": "1"}))

    assert by_exam["total"] == 2
    assert [batch["taskId"] for batch in by_exam["batches"]] == ["batch-task-1", "batch-task-2"]
    assert [batch["taskId"] for batch in by_external["batches"]] == ["batch-task-3"]
    assert paged["total"] == 3
    assert paged["limit"] == 1
    assert paged["offset"] == 1
    assert [batch["taskId"] for batch in paged["batches"]] == ["batch-task-2"]


def test_batch_task_alias_uses_same_submit_handler(monkeypatch, tmp_path):
    service, _store = _service(tmp_path)
    monkeypatch.setattr(robyn_app, "_BATCH_SERVICE", service)

    response = robyn_app.create_batch_task(DummyRequest(json_payload=_payload()))

    assert response == {"taskId": "batch-task-1", "examId": "exam-1", "status": "pending"}


def test_default_batch_service_wires_real_omr_runner(monkeypatch, tmp_path):
    cos_root = tmp_path / "cos"
    (cos_root / "incoming").mkdir(parents=True)
    (cos_root / "incoming" / "sheet-1.png").write_bytes(b"fake-image")
    service_config = ServiceConfig(
        storage=StorageConfig(
            service_data_dir=tmp_path / "service_data",
            template_dir=tmp_path / "templates",
        ),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'omr_service.db'}"),
    )
    runner_calls = []

    def fake_run_omr_directory(input_dir, output_dir):
        runner_calls.append((Path(input_dir), Path(output_dir)))
        checked_image = Path(output_dir) / "CheckedOMRs" / "sheet-1.png"
        checked_image.parent.mkdir(parents=True)
        checked_image.write_bytes(b"checked")
        return OmrRunResult(
            input_dir=Path(input_dir),
            output_dir=Path(output_dir),
            results_csv=None,
            rows=[{"file_id": "sheet-1.png", "answers": {"q1": "A"}}],
        )

    monkeypatch.setattr(robyn_app, "load_service_config", lambda: service_config)
    monkeypatch.setattr(robyn_app, "build_cos_client", lambda _config: LocalCosClient(cos_root))
    monkeypatch.setattr(robyn_app, "run_omr_directory", fake_run_omr_directory)

    service = robyn_app._build_batch_service()
    service.task_id_factory = lambda: "batch-task-1"
    service.submit_batch(BatchRecognitionRequest.from_api_json(_payload()))

    result = service.process_batch("batch-task-1")

    assert result.status == "completed"
    assert result.sheets[0].result["answers"] == {"q1": "A"}
    assert Path(result.sheets[0].result["checkedImagePath"]).parts[-2:] == ("CheckedOMRs", "sheet-1.png")
    assert len(runner_calls) == 1
