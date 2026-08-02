# Robyn Batch Callback Task Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add callback-based completion delivery and task execution record querying to the existing Robyn OMR task API while preserving current async task behavior.

**Architecture:** Keep `web/robyn_app.py` as the Robyn HTTP boundary and keep `src/services/omr_service.py` as the framework-independent recognition wrapper. Add small pure helpers in the Robyn layer for request metadata extraction, task filtering, task summary rendering, terminal payload rendering, and callback delivery so they can be unit-tested without running Robyn or the real OMR pipeline.

**Tech Stack:** Python 3, Robyn, pytest, `urllib.request` from the standard library for callback POSTs, existing `ThreadPoolExecutor` task execution.

---

## File Structure

- Modify: `web/robyn_app.py`
  - Add `GET /api/omr/tasks` list endpoint.
  - Parse `callback_url`, `external_task_id`, and `batch_id` from multipart form or JSON bodies.
  - Track `started_at`, `completed_at`, and callback state in task records.
  - Send callback payload after task reaches `completed` or `failed`.
  - Add pure helper functions: `_extract_request_metadata`, `_make_callback_state`, `_task_matches_filters`, `_task_summary`, `_list_tasks_response`, `_terminal_task_payload`, `_post_callback`, `_deliver_callback`.
- Create: `src/tests/test_robyn_app_task_records.py`
  - Unit-test helper behavior and task completion logic without starting the Robyn server.
  - Stub futures and run results.
  - Monkeypatch callback sender to avoid external network calls.
- No changes: `src/services/omr_service.py`
  - Current service wrapper remains the source of truth for recognition output.

## Task 1: Add Tests for Metadata Extraction and Callback State

**Files:**
- Create: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`

- [ ] **Step 1: Write failing tests**

Create `src/tests/test_robyn_app_task_records.py` with this content:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import web.robyn_app as robyn_app


@dataclass
class FakeRequest:
    files: dict[str, Any] | None = None
    body: bytes | None = None
    form_data: dict[str, str] | None = None
    payload: dict[str, Any] | None = None

    def json(self) -> dict[str, Any]:
        return self.payload or {}


def test_extract_request_metadata_from_json_body():
    request = FakeRequest(
        body=b"{}",
        payload={
            "input_dir": "inputs",
            "callback_url": "https://java.example.com/omr/callback",
            "external_task_id": "java-task-001",
            "batch_id": "batch-001",
        },
    )

    metadata = robyn_app._extract_request_metadata(request)

    assert metadata == {
        "callback_url": "https://java.example.com/omr/callback",
        "external_task_id": "java-task-001",
        "batch_id": "batch-001",
    }


def test_extract_request_metadata_from_form_data():
    request = FakeRequest(
        files={"file": b"pdf-bytes"},
        form_data={
            "callback_url": "https://java.example.com/omr/callback",
            "external_task_id": "java-task-002",
            "batch_id": "batch-002",
        },
    )

    metadata = robyn_app._extract_request_metadata(request)

    assert metadata == {
        "callback_url": "https://java.example.com/omr/callback",
        "external_task_id": "java-task-002",
        "batch_id": "batch-002",
    }


def test_extract_request_metadata_rejects_non_http_callback_url():
    request = FakeRequest(
        body=b"{}",
        payload={"input_dir": "inputs", "callback_url": "file:///tmp/callback"},
    )

    try:
        robyn_app._extract_request_metadata(request)
    except ValueError as exc:
        assert "callback_url must start with http:// or https://" in str(exc)
    else:
        raise AssertionError("Expected invalid callback_url to raise ValueError")


def test_make_callback_state_without_url():
    assert robyn_app._make_callback_state(None) == {
        "url": None,
        "status": "disabled",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
    }


def test_make_callback_state_with_url():
    assert robyn_app._make_callback_state("https://java.example.com/callback") == {
        "url": "https://java.example.com/callback",
        "status": "pending",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: FAIL because `_extract_request_metadata` and `_make_callback_state` do not exist.

- [ ] **Step 3: Implement metadata helpers**

In `web/robyn_app.py`, add this import near the other imports:

```python
from urllib.parse import urlparse
```

Add these helper functions after `_extract_file_bytes`:

```python
def _extract_request_metadata(request: Request) -> dict[str, str | None]:
    payload: dict[str, Any] = {}
    body = getattr(request, "body", None)
    if body:
        payload.update(request.json())

    form_data = getattr(request, "form_data", None) or getattr(request, "form", None) or {}
    if form_data:
        payload.update(form_data)

    callback_url = _clean_optional_string(payload.get("callback_url"))
    if callback_url is not None:
        parsed = urlparse(callback_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("callback_url must start with http:// or https://")
        if not parsed.netloc:
            raise ValueError("callback_url must include a host")

    return {
        "callback_url": callback_url,
        "external_task_id": _clean_optional_string(payload.get("external_task_id")),
        "batch_id": _clean_optional_string(payload.get("batch_id")),
    }


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS for the five tests in this task.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py
git commit -m "feat: parse robyn task callback metadata"
```

## Task 2: Add Tests for Task Filtering and Task List Summaries

**Files:**
- Modify: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`

- [ ] **Step 1: Add failing tests**

Append this code to `src/tests/test_robyn_app_task_records.py`:

```python
def test_task_matches_status_batch_and_external_filters():
    task = {
        "task_id": "task-1",
        "status": "completed",
        "external_task_id": "java-task-001",
        "batch_id": "batch-001",
    }

    assert robyn_app._task_matches_filters(task, {"status": "completed"}) is True
    assert robyn_app._task_matches_filters(task, {"status": "failed"}) is False
    assert robyn_app._task_matches_filters(task, {"batch_id": "batch-001"}) is True
    assert robyn_app._task_matches_filters(task, {"batch_id": "batch-002"}) is False
    assert robyn_app._task_matches_filters(task, {"external_task_id": "java-task-001"}) is True
    assert robyn_app._task_matches_filters(task, {"external_task_id": "java-task-404"}) is False


def test_task_summary_excludes_full_result_rows():
    task = {
        "task_id": "task-1",
        "status": "completed",
        "external_task_id": "java-task-001",
        "batch_id": "batch-001",
        "created_at": "2026-08-02T03:20:00Z",
        "updated_at": "2026-08-02T03:25:00Z",
        "completed_at": "2026-08-02T03:25:00Z",
        "callback": {"status": "delivered"},
        "result": {"count": 2, "results": [{"file_id": "a.png"}, {"file_id": "b.png"}]},
    }

    summary = robyn_app._task_summary(task)

    assert summary == {
        "task_id": "task-1",
        "external_task_id": "java-task-001",
        "batch_id": "batch-001",
        "status": "completed",
        "created_at": "2026-08-02T03:20:00Z",
        "updated_at": "2026-08-02T03:25:00Z",
        "completed_at": "2026-08-02T03:25:00Z",
        "result_count": 2,
        "callback_status": "delivered",
        "links": {"self": "/api/omr/tasks/task-1"},
    }
    assert "results" not in summary


def test_list_tasks_response_filters_and_paginates():
    tasks = [
        {"task_id": "task-1", "status": "completed", "batch_id": "batch-1", "result": {"count": 1}},
        {"task_id": "task-2", "status": "failed", "batch_id": "batch-1", "result": None},
        {"task_id": "task-3", "status": "completed", "batch_id": "batch-2", "result": {"count": 3}},
    ]

    response = robyn_app._list_tasks_response(
        tasks,
        filters={"status": "completed"},
        limit=1,
        offset=1,
    )

    assert response["total"] == 2
    assert response["limit"] == 1
    assert response["offset"] == 1
    assert [task["task_id"] for task in response["tasks"]] == ["task-3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: FAIL because `_task_matches_filters`, `_task_summary`, and `_list_tasks_response` do not exist.

- [ ] **Step 3: Implement task list helpers**

Add these helper functions to `web/robyn_app.py` after `_make_callback_state`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py
git commit -m "feat: add robyn task list summaries"
```

## Task 3: Add Task List Route and Metadata to Created Tasks

**Files:**
- Modify: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`

- [ ] **Step 1: Add failing tests**

Append this code to `src/tests/test_robyn_app_task_records.py`:

```python
def test_get_tasks_lists_current_registry(monkeypatch):
    monkeypatch.setattr(
        robyn_app,
        "_TASKS",
        {
            "task-1": {"task_id": "task-1", "status": "completed", "batch_id": "batch-1", "result": {"count": 1}},
            "task-2": {"task_id": "task-2", "status": "failed", "batch_id": "batch-1", "result": None},
        },
    )

    response = robyn_app.get_tasks(status="completed", batch_id=None, external_task_id=None, limit="50", offset="0")

    assert response["total"] == 1
    assert response["tasks"][0]["task_id"] == "task-1"


def test_create_task_response_includes_external_task_and_batch(monkeypatch, tmp_path):
    class ImmediateFuture:
        def add_done_callback(self, callback):
            self.callback = callback

        def running(self):
            return False

    future = ImmediateFuture()
    monkeypatch.setattr(robyn_app._EXECUTOR, "submit", lambda *args, **kwargs: future)
    monkeypatch.setattr(
        robyn_app,
        "_prepare_task_input",
        lambda request: (tmp_path / "input", tmp_path / "tasks" / "task-1" / "output", "upload.pdf"),
    )
    monkeypatch.setattr(
        robyn_app,
        "_extract_request_metadata",
        lambda request: {
            "callback_url": "https://java.example.com/callback",
            "external_task_id": "java-task-001",
            "batch_id": "batch-001",
        },
    )
    robyn_app._TASKS.clear()

    response = robyn_app.create_task(FakeRequest())

    assert response["task_id"] == "task-1"
    assert response["external_task_id"] == "java-task-001"
    assert response["batch_id"] == "batch-001"
    stored = robyn_app._TASKS["task-1"]
    assert stored["callback"]["url"] == "https://java.example.com/callback"
    assert stored["started_at"] is None
    assert stored["completed_at"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: FAIL because `get_tasks` route is missing and `create_task` does not store metadata yet.

- [ ] **Step 3: Implement route and task metadata**

In `web/robyn_app.py`, add this route before `get_task` so `/api/omr/tasks` is distinct from `/api/omr/tasks/:task_id`:

```python
@app.get("/api/omr/tasks")
def get_tasks(
    status: str | None = None,
    batch_id: str | None = None,
    external_task_id: str | None = None,
    limit: str = "50",
    offset: str = "0",
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    with _TASK_LOCK:
        tasks = list(_TASKS.values())
    return _list_tasks_response(
        tasks,
        filters={
            "status": _clean_optional_string(status),
            "batch_id": _clean_optional_string(batch_id),
            "external_task_id": _clean_optional_string(external_task_id),
        },
        limit=safe_limit,
        offset=safe_offset,
    )
```

Modify `create_task` so the body starts like this:

```python
    try:
        metadata = _extract_request_metadata(request)
        input_dir, output_dir, upload_name = _prepare_task_input(request)
        task_id = output_dir.parent.name
        future = _EXECUTOR.submit(run_omr_directory, input_dir, output_dir)
        now = _now_iso()
        _store_task(
            task_id,
            {
                "task_id": task_id,
                "external_task_id": metadata["external_task_id"],
                "batch_id": metadata["batch_id"],
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "input_dir": str(input_dir),
                "output_dir": str(output_dir),
                "upload_name": upload_name,
                "callback": _make_callback_state(metadata["callback_url"]),
                "result": None,
                "error": None,
                "future": future,
            },
        )
```

Modify the return value in `create_task` to include metadata:

```python
        return {
            "task_id": task_id,
            "external_task_id": metadata["external_task_id"],
            "batch_id": metadata["batch_id"],
            "status": "queued",
            "links": {
                "self": f"/api/omr/tasks/{task_id}",
            },
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py
git commit -m "feat: expose robyn task records endpoint"
```

## Task 4: Add Completion Timestamps and Terminal Payload Helper

**Files:**
- Modify: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`

- [ ] **Step 1: Add failing tests**

Append this code to `src/tests/test_robyn_app_task_records.py`:

```python
class FakeRunResult:
    def to_dict(self):
        return {
            "results_csv": "service_data/tasks/task-1/output/Results/Results_10AM.csv",
            "count": 1,
            "results": [{"file_id": "checked.png"}],
        }


class CompletedFuture:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def result(self):
        if self._error:
            raise self._error
        return self._result


def test_complete_task_records_completed_terminal_payload(monkeypatch):
    monkeypatch.setattr(robyn_app, "_deliver_callback", lambda task: None)
    robyn_app._TASKS.clear()
    robyn_app._TASKS["task-1"] = {
        "task_id": "task-1",
        "status": "queued",
        "created_at": "created",
        "updated_at": "created",
        "started_at": None,
        "completed_at": None,
        "output_dir": "service_data/tasks/task-1/output",
        "callback": robyn_app._make_callback_state(None),
        "result": None,
        "error": None,
    }

    robyn_app._complete_task("task-1", CompletedFuture(result=FakeRunResult()))

    task = robyn_app._TASKS["task-1"]
    assert task["status"] == "completed"
    assert task["completed_at"] is not None
    assert task["result"]["results"][0]["checked_image_url"] == "/api/omr/tasks/task-1/checked-image/checked.png"
    payload = robyn_app._terminal_task_payload(task)
    assert payload["status"] == "completed"
    assert payload["result"]["count"] == 1
    assert "future" not in payload


def test_complete_task_records_failed_terminal_payload(monkeypatch):
    monkeypatch.setattr(robyn_app, "_deliver_callback", lambda task: None)
    robyn_app._TASKS.clear()
    robyn_app._TASKS["task-2"] = {
        "task_id": "task-2",
        "status": "queued",
        "created_at": "created",
        "updated_at": "created",
        "started_at": None,
        "completed_at": None,
        "output_dir": "service_data/tasks/task-2/output",
        "callback": robyn_app._make_callback_state(None),
        "result": None,
        "error": None,
    }

    robyn_app._complete_task("task-2", CompletedFuture(error=RuntimeError("boom")))

    task = robyn_app._TASKS["task-2"]
    assert task["status"] == "failed"
    assert task["completed_at"] is not None
    assert task["error"] == "boom"
    payload = robyn_app._terminal_task_payload(task)
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert payload["error"] == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: FAIL because `_terminal_task_payload` does not exist and `_complete_task` does not set `completed_at`.

- [ ] **Step 3: Implement terminal payload and completion timestamps**

Add this helper near `_public_task`:

```python
def _terminal_task_payload(task: dict[str, Any]) -> dict[str, Any]:
    return _public_task(task)
```

Modify `_complete_task` to compute the completion time and call callback after releasing the lock:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py
git commit -m "feat: record robyn task terminal state"
```

## Task 5: Add Callback Delivery Helper with Retry State

**Files:**
- Modify: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`

- [ ] **Step 1: Add failing tests**

Append this code to `src/tests/test_robyn_app_task_records.py`:

```python
def test_deliver_callback_marks_disabled_callback_unchanged():
    task = {
        "task_id": "task-1",
        "status": "completed",
        "callback": robyn_app._make_callback_state(None),
        "result": {"count": 1},
        "error": None,
    }

    robyn_app._deliver_callback(task, post_callback=lambda url, payload: None, max_attempts=3)

    assert task["callback"]["status"] == "disabled"
    assert task["callback"]["attempts"] == 0


def test_deliver_callback_marks_delivered_after_success():
    calls = []
    task = {
        "task_id": "task-1",
        "status": "completed",
        "callback": robyn_app._make_callback_state("https://java.example.com/callback"),
        "result": {"count": 1},
        "error": None,
    }

    def fake_post(url, payload):
        calls.append((url, payload))

    robyn_app._deliver_callback(task, post_callback=fake_post, max_attempts=3)

    assert len(calls) == 1
    assert calls[0][0] == "https://java.example.com/callback"
    assert calls[0][1]["task_id"] == "task-1"
    assert task["callback"]["status"] == "delivered"
    assert task["callback"]["attempts"] == 1
    assert task["callback"]["last_error"] is None
    assert task["callback"]["last_attempt_at"] is not None


def test_deliver_callback_records_failure_after_retries():
    task = {
        "task_id": "task-1",
        "status": "failed",
        "callback": robyn_app._make_callback_state("https://java.example.com/callback"),
        "result": None,
        "error": "boom",
    }

    def fake_post(url, payload):
        raise RuntimeError("HTTP 500")

    robyn_app._deliver_callback(task, post_callback=fake_post, max_attempts=2)

    assert task["callback"]["status"] == "failed"
    assert task["callback"]["attempts"] == 2
    assert task["callback"]["last_error"] == "HTTP 500"
    assert task["status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: FAIL because `_deliver_callback` does not support injectable sender and retry state.

- [ ] **Step 3: Implement callback delivery**

Add these imports near the top of `web/robyn_app.py`:

```python
import json
from urllib import request as urllib_request
```

Add these helpers near `_terminal_task_payload`:

```python
def _post_callback(url: str, payload: dict[str, Any], timeout: float = 10.0) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        status_code = getattr(response, "status", 200)
        if status_code >= 400:
            raise RuntimeError(f"HTTP {status_code}")


def _deliver_callback(
    task: dict[str, Any],
    *,
    post_callback=_post_callback,
    max_attempts: int = 3,
) -> None:
    callback = task.get("callback") or {}
    callback_url = callback.get("url")
    if not callback_url:
        return

    payload = _terminal_task_payload(task)
    for _ in range(max_attempts):
        callback["attempts"] = int(callback.get("attempts") or 0) + 1
        callback["last_attempt_at"] = _now_iso()
        try:
            post_callback(callback_url, payload)
        except Exception as exc:
            callback["status"] = "failed"
            callback["last_error"] = str(exc)
        else:
            callback["status"] = "delivered"
            callback["last_error"] = None
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py
git commit -m "feat: deliver robyn task callbacks"
```

## Task 6: Verify Full Web Layer Compatibility

**Files:**
- Modify: `src/tests/test_robyn_app_task_records.py`
- Modify: `web/robyn_app.py`
- Modify: `docs/robyn-web-service.md`

- [ ] **Step 1: Add compatibility tests for existing endpoints helpers**

Append this code to `src/tests/test_robyn_app_task_records.py`:

```python
def test_health_response_remains_compatible():
    response = robyn_app.health()

    assert response["status"] == "ok"
    assert response["service"] == "omrchecker-robyn"
    assert "workers" in response
    assert "template_dir" in response


def test_public_task_hides_future_and_reports_running_status():
    class RunningFuture:
        def running(self):
            return True

    public = robyn_app._public_task(
        {
            "task_id": "task-1",
            "status": "queued",
            "future": RunningFuture(),
            "result": None,
        }
    )

    assert public["status"] == "running"
    assert "future" not in public
```

- [ ] **Step 2: Run focused web tests**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 3: Update local Robyn API documentation**

In `docs/robyn-web-service.md`, update these sections:

1. In `Goals`, add:

```markdown
- Support optional callback delivery for long-running recognition tasks.
- Support task execution record queries for compensation and audit.
```

2. In `Submit a PDF or image`, add after line describing one file field:

```markdown
Optional fields:

- `callback_url`: completion callback endpoint. If supplied, the service posts the terminal task payload to this URL.
- `external_task_id`: caller-side task ID returned in task responses and callbacks.
- `batch_id`: caller-side batch ID used by task list filtering.
```

3. In the submit response example, include:

```json
{
  "task_id": "a1b2c3...",
  "external_task_id": "java-task-001",
  "batch_id": "batch-20260802-001",
  "status": "queued",
  "links": {
    "self": "/api/omr/tasks/a1b2c3..."
  }
}
```

4. Add a new section after `Query task`:

```markdown
### Query task execution records

```http
GET /api/omr/tasks?status=completed&batch_id=batch-20260802-001&limit=50&offset=0
```

Response:

```json
{
  "total": 1,
  "limit": 50,
  "offset": 0,
  "tasks": [
    {
      "task_id": "a1b2c3...",
      "external_task_id": "java-task-001",
      "batch_id": "batch-20260802-001",
      "status": "completed",
      "created_at": "2026-08-02T03:20:00Z",
      "updated_at": "2026-08-02T03:25:00Z",
      "completed_at": "2026-08-02T03:25:00Z",
      "result_count": 1,
      "callback_status": "delivered",
      "links": {
        "self": "/api/omr/tasks/a1b2c3..."
      }
    }
  ]
}
```
```

5. Add a new section after task records:

```markdown
### Callback payload

When `callback_url` is supplied, Robyn posts the terminal task payload to that URL when the task reaches `completed` or `failed`. The payload shape matches `GET /api/omr/tasks/{task_id}` so Java can reuse the same DTO. Callback failure does not change the recognition task status. The caller can still query the task by `task_id`.
```

- [ ] **Step 4: Run full relevant tests**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py src/tests/test_all_samples.py::test_run_sample1 -q
```

Expected: PASS. This validates the new Web helper tests and one existing CLI sample still works.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_task_records.py docs/robyn-web-service.md
git commit -m "docs: update robyn callback api contract"
```

## Task 7: Final Verification and Status Summary

**Files:**
- No code changes expected.

- [ ] **Step 1: Run focused tests**

Run:

```bash
rtk pytest src/tests/test_robyn_app_task_records.py -q
```

Expected: PASS.

- [ ] **Step 2: Run a representative existing sample test**

Run:

```bash
rtk pytest src/tests/test_all_samples.py::test_run_sample1 -q
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run:

```bash
rtk git diff --stat HEAD
rtk git status --short
```

Expected: only unrelated pre-existing dirty files remain. New Robyn callback work should be committed.

- [ ] **Step 4: Summarize implementation**

Report these points to the user:

```markdown
完成：
- `POST /api/omr/tasks` 支持 `callback_url`、`external_task_id`、`batch_id`。
- 任务终态会回调，失败可通过查询补偿。
- 新增 `GET /api/omr/tasks` 查询执行记录。
- 保持现有 Robyn、CLI 识别流程、CSV 和 checked image 下载兼容。

验证：
- `rtk pytest src/tests/test_robyn_app_task_records.py -q`
- `rtk pytest src/tests/test_all_samples.py::test_run_sample1 -q`
```

## Self-Review

Spec coverage:

- Callback support: Task 1 parses `callback_url`, Task 5 delivers terminal payload.
- Task execution record query: Task 2 adds summary/filter helpers, Task 3 exposes `GET /api/omr/tasks`.
- Preserve polling compensation: Task 4 keeps terminal payload available through task detail.
- Compatibility: Task 6 explicitly tests `health` and `_public_task`, and updates docs.
- No recognition algorithm changes: plan does not modify `src/services/omr_service.py`.
- Batch semantics: Task 3 stores `batch_id`; list endpoint filters by it.

Placeholder scan:

- No placeholder markers or undefined vague implementation steps remain.

Type consistency:

- Metadata keys are consistently `callback_url`, `external_task_id`, and `batch_id`.
- Callback state keys are consistently `url`, `status`, `attempts`, `last_error`, and `last_attempt_at`.
- Route helper names are consistently `_extract_request_metadata`, `_make_callback_state`, `_task_matches_filters`, `_task_summary`, `_list_tasks_response`, `_terminal_task_payload`, `_post_callback`, and `_deliver_callback`.
