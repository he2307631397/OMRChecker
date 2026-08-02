"""Robyn Web API for OMRChecker.

Run with:
    python web/robyn_app.py

The API is intentionally thin. Recognition logic lives in ``src.services.omr_service``
so it can be tested without Robyn and reused by other front ends.
"""

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from urllib.parse import urlparse
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

app = Robyn(__file__)

_MAX_WORKERS = int(os.getenv("OMR_SERVICE_WORKERS", "1"))
_SERVICE_DATA_DIR = Path(os.getenv("OMR_SERVICE_DATA_DIR", str(DEFAULT_SERVICE_DATA_DIR)))
_TEMPLATE_DIR = Path(os.getenv("OMR_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR)))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="omr-worker")
_TASKS: dict[str, dict[str, Any]] = {}
_TASK_LOCK = Lock()


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
        input_dir, output_dir, upload_name = _prepare_task_input(request)
        task_id = output_dir.parent.name
        future = _EXECUTOR.submit(run_omr_directory, input_dir, output_dir)
        _store_task(
            task_id,
            {
                "task_id": task_id,
                "status": "queued",
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
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
            "links": {
                "self": f"/api/omr/tasks/{task_id}",
            },
        }
    except Exception as exc:  # Robyn will serialize this response for clients.
        return {"status": "failed", "error": str(exc)}


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

    body = getattr(request, "body", None)
    if body:
        json_payload = request.json()
        if isinstance(json_payload, dict):
            payload.update(json_payload)

    for form_attr in ("form_data", "form"):
        form_payload = getattr(request, form_attr, None)
        if form_payload:
            payload.update(dict(form_payload))

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


def _make_callback_state(callback_url: str | None) -> dict[str, Any]:
    return {
        "url": callback_url,
        "status": "pending" if callback_url else "disabled",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
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
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return
        task["updated_at"] = _now_iso()
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
