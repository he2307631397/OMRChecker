"""Robyn Web API for OMRChecker.

Run with:
    python web/robyn_app.py

The API is intentionally thin. Recognition logic lives in ``src.services.omr_service``
so it can be tested without Robyn and reused by other front ends.
"""

import copy
import json
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.parse import urlparse
import urllib.request as urllib_request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from robyn import Request, Robyn, serve_file

from src.services.omr_service import (
    DEFAULT_SERVICE_DATA_DIR,
    DEFAULT_TEMPLATE_DIR,
    get_checked_image_path,
    prepare_upload_input_dir,
    run_omr_directory,
)
from src.services.batch_models import BatchRecognitionRequest, render_callback_payload_from_records
from src.services.batch_service import BatchRecognitionService, RecognitionContext, RecognitionOutput
from src.services.cos_client import build_cos_client
from src.services.service_config import load_service_config
from src.services.task_store import TaskStore

app = Robyn(__file__)

_MAX_WORKERS = int(os.getenv("OMR_SERVICE_WORKERS", "1"))
_SERVICE_DATA_DIR = Path(os.getenv("OMR_SERVICE_DATA_DIR", str(DEFAULT_SERVICE_DATA_DIR)))
_TEMPLATE_DIR = Path(os.getenv("OMR_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR)))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="omr-worker")
_TASKS: dict[str, dict[str, Any]] = {}
_TASK_LOCK = Lock()


class HttpCallbackClient:
    def __init__(self, *, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload.get("taskId")
        batch = _BATCH_SERVICE.store.get_batch(str(task_id)) if task_id else None
        url = batch.get("callback_url") if batch else None
        if not url:
            return {"success": False, "error": "callback url not found"}
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
            status_code = getattr(response, "status", response.getcode())
            response_text = response.read().decode("utf-8", errors="replace")
            return {
                "success": status_code < 400,
                "status_code": status_code,
                "response_text": response_text,
            }


def _sqlite_path_from_url(url: str) -> Path:
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    if url.startswith("sqlite://"):
        return Path(url.removeprefix("sqlite://"))
    return Path(url)


def _build_batch_service() -> BatchRecognitionService:
    config = load_service_config()
    db_path = _sqlite_path_from_url(config.database.url or "sqlite:///service_data/omr_service.db")
    store = TaskStore(db_path)
    store.initialize()
    return BatchRecognitionService(
        store=store,
        object_storage=build_cos_client(config.cos),
        config=config,
        recognition_runner=_run_batch_omr,
        callback_client=HttpCallbackClient(timeout_seconds=config.callback.timeout_seconds),
    )


def _run_batch_omr(context: RecognitionContext) -> RecognitionOutput:
    output_dir = context.workdir / "output"
    result = run_omr_directory(context.workdir, output_dir)
    result_payload = result.rows[0] if len(result.rows) == 1 else result.to_dict()
    checked_image_path = _checked_image_path_for_result(output_dir, result_payload)
    if checked_image_path is not None and isinstance(result_payload, dict):
        result_payload = dict(result_payload)
        result_payload["checkedImagePath"] = str(checked_image_path)
    return RecognitionOutput(result=result_payload, checked_image_path=checked_image_path)


def _checked_image_path_for_result(output_dir: Path, result_payload: dict[str, Any] | Any) -> Path | None:
    if not isinstance(result_payload, dict):
        return None
    file_id = result_payload.get("file_id")
    if not file_id:
        return None
    return get_checked_image_path(output_dir, str(file_id))


_BATCH_SERVICE = _build_batch_service()
_BATCH_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="omr-batch-worker")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "omrchecker-robyn",
        "workers": _MAX_WORKERS,
        "template_dir": str(_TEMPLATE_DIR),
    }


@app.post("/api/omr/tasks")
def create_task(request: Request) -> dict[str, Any]:
    """Create an asynchronous OMR recognition task.

    Supported inputs:
    - multipart/form-data with a file field, recommended for Java integration.
    - application/json with ``input_dir`` for internal testing or trusted servers.
    """

    try:
        metadata = _extract_request_metadata(request)
        input_dir, output_dir, upload_name = _prepare_task_input(request)
        task_id = output_dir.parent.name
        now = _now_iso()
        future = _EXECUTOR.submit(run_omr_directory, input_dir, output_dir)
        _store_task(
            task_id,
            {
                "task_id": task_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "external_task_id": metadata["external_task_id"],
                "batch_id": metadata["batch_id"],
                "callback": _make_callback_state(metadata["callback_url"]),
                "input_dir": str(input_dir),
                "output_dir": str(output_dir),
                "upload_name": upload_name,
                "result": None,
                "error": None,
                "future": future,
            },
        )
        future.add_done_callback(lambda done_future: _complete_task(task_id, done_future))
        return {
            "task_id": task_id,
            "status": "queued",
            "external_task_id": metadata["external_task_id"],
            "batch_id": metadata["batch_id"],
            "links": {
                "self": f"/api/omr/tasks/{task_id}",
            },
        }
    except Exception as exc:  # Robyn will serialize this response for clients.
        return {"status": "failed", "error": str(exc)}


@app.post("/api/omr/batches")
def create_batch(request: Request) -> dict[str, Any]:
    try:
        batch_request = BatchRecognitionRequest.from_api_json(_json_request_body(request))
        result = _BATCH_SERVICE.submit_batch(batch_request)
        _BATCH_EXECUTOR.submit(_process_batch_safely, result.task_id)
        return result.to_callback_dict()
    except ValueError as exc:
        return {"status": "failed", "error": str(exc)}


@app.post("/api/omr/batch-tasks")
def create_batch_task(request: Request) -> dict[str, Any]:
    return create_batch(request)


@app.get("/api/omr/batches")
def get_batches(request: Request) -> dict[str, Any]:
    query_params = getattr(request, "query_params", None) or getattr(request, "queries", None) or {}
    filters = {
        "status": _clean_optional_string(query_params.get("status")),
        "exam_id": _clean_optional_string(query_params.get("examId") or query_params.get("exam_id")),
        "external_batch_id": _clean_optional_string(
            query_params.get("externalBatchId") or query_params.get("external_batch_id")
        ),
    }
    limit = _positive_int(query_params.get("limit"), default=50)
    offset = _nonnegative_int(query_params.get("offset"), default=0)
    batches = _BATCH_SERVICE.store.list_batches(
        status=filters["status"],
        exam_id=filters["exam_id"],
        external_batch_id=filters["external_batch_id"],
    )
    page = batches[offset : offset + limit]
    return {
        "total": len(batches),
        "limit": limit,
        "offset": offset,
        "batches": [_batch_summary(batch) for batch in page],
    }


@app.get("/api/omr/batches/:task_id")
def get_batch(task_id: str) -> dict[str, Any]:
    batch = _BATCH_SERVICE.store.get_batch(task_id)
    if batch is None:
        return {"status": "not_found", "taskId": task_id, "error": "batch not found"}
    return _batch_payload_from_store(task_id)


@app.get("/api/omr/tasks")
def get_tasks(request: Request) -> dict[str, Any]:
    query_params = getattr(request, "query_params", None) or getattr(request, "queries", None) or {}
    filters = {
        "status": _clean_optional_string(query_params.get("status")),
        "batch_id": _clean_optional_string(query_params.get("batch_id")),
        "external_task_id": _clean_optional_string(query_params.get("external_task_id")),
    }
    limit = _positive_int(query_params.get("limit"), default=50)
    offset = _nonnegative_int(query_params.get("offset"), default=0)
    with _TASK_LOCK:
        tasks = list(_TASKS.values())
    return _list_tasks_response(tasks, filters=filters, limit=limit, offset=offset)


@app.get("/api/omr/tasks/:task_id")
def get_task(task_id: str) -> dict[str, Any]:
    task = _get_task(task_id)
    if task is None:
        return {"status": "not_found", "task_id": task_id}
    return _public_task(task)


@app.get("/api/omr/tasks/:task_id/checked-image/:file_id")
def get_checked_image(task_id: str, file_id: str):
    task = _get_task(task_id)
    if task is None:
        return {"status": "not_found", "task_id": task_id}
    image_path = get_checked_image_path(task["output_dir"], file_id)
    if image_path is None:
        return {"status": "not_found", "task_id": task_id, "file_id": file_id}
    return serve_file(str(image_path), file_name=Path(file_id).name)


@app.get("/api/omr/tasks/:task_id/results-csv")
def get_results_csv(task_id: str):
    task = _get_task(task_id)
    if task is None:
        return {"status": "not_found", "task_id": task_id}
    result = task.get("result") or {}
    results_csv = result.get("results_csv")
    if not results_csv:
        return {"status": "not_found", "task_id": task_id, "file": "results_csv"}
    return serve_file(results_csv, file_name=Path(results_csv).name)


def _prepare_task_input(request: Request) -> tuple[Path, Path, str | None]:
    files = getattr(request, "files", None) or {}
    if files:
        file_name, file_content = next(iter(files.items()))
        file_bytes = _extract_file_bytes(file_content)
        task_id, input_dir, output_dir = prepare_upload_input_dir(
            file_name,
            file_bytes,
            template_dir=_TEMPLATE_DIR,
            service_data_dir=_SERVICE_DATA_DIR,
        )
        return input_dir, output_dir, file_name

    body = getattr(request, "body", None)
    if body:
        payload = request.json()
        if "input_dir" not in payload:
            raise ValueError("JSON requests must include input_dir")
        task_id = str(payload.get("task_id") or output_safe_task_id())
        output_dir = _SERVICE_DATA_DIR / "tasks" / task_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        return Path(payload["input_dir"]), output_dir, None

    raise ValueError("Upload a file using multipart/form-data or send JSON with input_dir")


def _json_request_body(request: Request) -> dict[str, Any]:
    try:
        payload = request.json()
    except Exception as exc:
        raise ValueError("invalid JSON request body") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be an object")
    return payload


def _process_batch_safely(task_id: str) -> None:
    try:
        _BATCH_SERVICE.process_batch(task_id)
    except Exception as exc:  # noqa: BLE001 - background failures must be persisted.
        try:
            _BATCH_SERVICE.store.update_batch_status(task_id, "failed", error=str(exc))
        except KeyError:
            return


def _batch_payload_from_store(task_id: str) -> dict[str, Any]:
    batch = _BATCH_SERVICE.store.get_batch(task_id)
    if batch is None:
        raise KeyError(f"batch not found: {task_id}")
    return render_callback_payload_from_records(
        batch=batch,
        sheets=_BATCH_SERVICE.store.list_sheets(task_id),
        artifacts=_BATCH_SERVICE.store.list_artifacts(task_id),
    )


def _batch_summary(batch: dict[str, Any]) -> dict[str, Any]:
    payload = _batch_payload_from_store(batch["task_id"])
    return {
        "taskId": payload["taskId"],
        "examId": payload["examId"],
        "externalBatchId": payload.get("externalBatchId"),
        "status": payload["status"],
        "aggregateCounts": payload["aggregateCounts"],
        "sheets": payload["sheets"],
        "createdAt": batch.get("created_at"),
        "updatedAt": batch.get("updated_at"),
        "completedAt": batch.get("completed_at"),
        "links": {"self": f"/api/omr/batches/{payload['taskId']}"},
    }


def _extract_file_bytes(file_content: Any) -> bytes:
    if isinstance(file_content, bytes):
        return file_content
    if isinstance(file_content, bytearray):
        return bytes(file_content)
    if hasattr(file_content, "content"):
        return bytes(file_content.content)
    if hasattr(file_content, "body"):
        return bytes(file_content.body)
    raise TypeError(f"Unsupported uploaded file object: {type(file_content)!r}")


def _extract_request_metadata(request: Request) -> dict[str, str | None]:
    payload: dict[str, Any] = {}

    for form_attr in ("form_data", "form"):
        form_payload = getattr(request, form_attr, None)
        if form_payload:
            payload.update(dict(form_payload))

    if not payload:
        body = getattr(request, "body", None)
        if body:
            try:
                json_payload = request.json()
            except Exception:
                json_payload = {}
            if isinstance(json_payload, dict):
                payload.update(json_payload)

    metadata = {
        "callback_url": _clean_optional_string(payload.get("callback_url")),
        "external_task_id": _clean_optional_string(payload.get("external_task_id")),
        "batch_id": _clean_optional_string(payload.get("batch_id")),
    }

    callback_url = metadata["callback_url"]
    if callback_url is not None:
        parsed_url = urlparse(callback_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("callback_url must start with http:// or https://")

    return metadata


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _nonnegative_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _make_callback_state(callback_url: str | None) -> dict[str, Any]:
    return {
        "url": callback_url,
        "status": "pending" if callback_url else "disabled",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
    }


def _task_matches_filters(task: dict[str, Any], filters: dict[str, str | None]) -> bool:
    for key in ("status", "batch_id", "external_task_id"):
        expected = filters.get(key)
        if expected and task.get(key) != expected:
            return False
    return True


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    result = task.get("result") or {}
    callback = task.get("callback") or {}
    task_id = task.get("task_id")
    return {
        "task_id": task_id,
        "external_task_id": task.get("external_task_id"),
        "batch_id": task.get("batch_id"),
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "completed_at": task.get("completed_at"),
        "result_count": result.get("count", 0),
        "callback_status": callback.get("status"),
        "links": {"self": f"/api/omr/tasks/{task_id}"},
    }


def _list_tasks_response(
    tasks: list[dict[str, Any]],
    *,
    filters: dict[str, str | None],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    filtered = [task for task in tasks if _task_matches_filters(task, filters)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "tasks": [_task_summary(task) for task in page],
    }


def output_safe_task_id() -> str:
    from src.services.omr_service import create_task_id

    return create_task_id()


def _store_task(task_id: str, task: dict[str, Any]) -> None:
    with _TASK_LOCK:
        _TASKS[task_id] = task


def _get_task(task_id: str) -> dict[str, Any] | None:
    with _TASK_LOCK:
        return _TASKS.get(task_id)


def _complete_task(task_id: str, future: Future) -> None:
    task_for_callback: dict[str, Any] | None = None
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return
        completed_at = _now_iso()
        task["updated_at"] = completed_at
        task["completed_at"] = completed_at
        try:
            result = future.result()
            result_dict = result.to_dict()
            for row in result_dict["results"]:
                file_id = row.get("file_id", "")
                if file_id:
                    row["checked_image_url"] = (
                        f"/api/omr/tasks/{task_id}/checked-image/{Path(file_id).name}"
                    )
            task["status"] = "completed"
            task["result"] = result_dict
        except Exception as exc:
            task["status"] = "failed"
            task["error"] = str(exc)
        task_for_callback = task
    _deliver_callback(task_for_callback)


def _post_callback(url: str, payload: dict[str, Any], timeout: float = 10.0) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", response.getcode())
        if status >= 400:
            raise RuntimeError(f"Callback POST failed with HTTP status {status}")


def _deliver_callback(
    task: dict[str, Any],
    *,
    post_callback=_post_callback,
    max_attempts: int = 3,
) -> None:
    callback = task.get("callback") or {}
    url = callback.get("url")
    if not url:
        return

    for _attempt in range(max_attempts):
        callback["attempts"] += 1
        callback["last_attempt_at"] = _now_iso()
        try:
            payload = copy.deepcopy(_terminal_task_payload(task))
            post_callback(url, payload)
        except Exception as exc:
            callback["last_error"] = str(exc)
            callback["status"] = "failed"
        else:
            callback["status"] = "delivered"
            callback["last_error"] = None
            return


def _terminal_task_payload(task: dict[str, Any]) -> dict[str, Any]:
    return _public_task(task)


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in task.items() if key != "future"}
    future = task.get("future")
    if task["status"] == "queued" and future is not None and future.running():
        public["status"] = "running"
    return public


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    port = int(os.getenv("OMR_SERVICE_PORT", "8080"))
    app.start(port=port)
