import pytest

import web.robyn_app as robyn_app
from web.robyn_app import _extract_request_metadata, _make_callback_state


class DummyRequest:
    def __init__(
        self,
        body=None,
        json_payload=None,
        form_data=None,
        form=None,
        json_error=None,
        query_params=None,
        files=None,
    ):
        self.body = body
        self._json_payload = json_payload
        self._json_error = json_error
        self.query_params = query_params or {}
        self.files = files or {}
        if form_data is not None:
            self.form_data = form_data
        if form is not None:
            self.form = form

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_payload


def test_extract_request_metadata_from_json_body_returns_optional_task_fields():
    request = DummyRequest(
        body=b'{"callback_url":"https://example.com/callback"}',
        json_payload={
            "callback_url": " https://example.com/callback ",
            "external_task_id": " ext-123 ",
            "batch_id": " batch-456 ",
        },
    )

    metadata = _extract_request_metadata(request)

    assert metadata == {
        "callback_url": "https://example.com/callback",
        "external_task_id": "ext-123",
        "batch_id": "batch-456",
    }


def test_extract_request_metadata_from_form_data_returns_optional_task_fields():
    request = DummyRequest(
        form_data={
            "callback_url": "http://example.com/callback",
            "external_task_id": "ext-789",
            "batch_id": "batch-012",
        }
    )

    metadata = _extract_request_metadata(request)

    assert metadata == {
        "callback_url": "http://example.com/callback",
        "external_task_id": "ext-789",
        "batch_id": "batch-012",
    }


def test_extract_request_metadata_from_form_data_with_non_json_body_returns_optional_task_fields():
    request = DummyRequest(
        body=b"------WebKitFormBoundary\r\nform-data",
        json_error=ValueError("not json"),
        form_data={
            "callback_url": "https://example.com/form-callback",
            "external_task_id": "form-ext-123",
            "batch_id": "form-batch-456",
        },
    )

    metadata = _extract_request_metadata(request)

    assert metadata == {
        "callback_url": "https://example.com/form-callback",
        "external_task_id": "form-ext-123",
        "batch_id": "form-batch-456",
    }


def test_extract_request_metadata_rejects_callback_url_without_http_scheme():
    request = DummyRequest(
        body=b'{"callback_url":"ftp://example.com/callback"}',
        json_payload={"callback_url": "ftp://example.com/callback"},
    )

    with pytest.raises(ValueError, match="callback_url must start with http:// or https://"):
        _extract_request_metadata(request)


def test_make_callback_state_without_url_is_disabled():
    assert _make_callback_state(None) == {
        "url": None,
        "status": "disabled",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
    }


def test_make_callback_state_with_url_is_pending():
    assert _make_callback_state("https://example.com/callback") == {
        "url": "https://example.com/callback",
        "status": "pending",
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
    }


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


class StubFuture:
    def __init__(self):
        self.done_callback = None

    def add_done_callback(self, callback):
        self.done_callback = callback

    def running(self):
        return False


def test_get_tasks_lists_current_registry_and_filters_by_status(monkeypatch):
    monkeypatch.setattr(
        robyn_app,
        "_TASKS",
        {
            "task-queued": {
                "task_id": "task-queued",
                "status": "queued",
                "created_at": "2026-08-02T03:30:00Z",
                "updated_at": "2026-08-02T03:30:00Z",
                "completed_at": None,
                "external_task_id": "external-queued",
                "batch_id": "batch-1",
                "callback": {"status": "pending"},
                "result": None,
            },
            "task-completed": {
                "task_id": "task-completed",
                "status": "completed",
                "created_at": "2026-08-02T03:31:00Z",
                "updated_at": "2026-08-02T03:32:00Z",
                "completed_at": None,
                "external_task_id": "external-completed",
                "batch_id": "batch-1",
                "callback": {"status": "disabled"},
                "result": {"count": 2},
            },
        },
    )

    unfiltered = robyn_app.get_tasks(DummyRequest())
    filtered = robyn_app.get_tasks(DummyRequest(query_params={"status": "completed"}))

    assert unfiltered["total"] == 2
    assert unfiltered["limit"] == 50
    assert {task["task_id"] for task in unfiltered["tasks"]} == {"task-queued", "task-completed"}
    assert filtered["total"] == 1
    assert [task["task_id"] for task in filtered["tasks"]] == ["task-completed"]


def test_create_task_response_and_stored_record_include_external_metadata(monkeypatch, tmp_path):
    future = StubFuture()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "tasks" / "task-from-output-dir" / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    monkeypatch.setattr(robyn_app, "_TASKS", {})
    monkeypatch.setattr(
        robyn_app,
        "_prepare_task_input",
        lambda request: (input_dir, output_dir, "upload.pdf"),
    )
    monkeypatch.setattr(robyn_app._EXECUTOR, "submit", lambda *args, **kwargs: future)

    response = robyn_app.create_task(
        DummyRequest(
            form_data={
                "callback_url": "https://example.com/callback",
                "external_task_id": "external-123",
                "batch_id": "batch-123",
            }
        )
    )

    task_id = response["task_id"]
    stored_task = robyn_app._TASKS[task_id]
    assert response["status"] == "queued"
    assert response["external_task_id"] == "external-123"
    assert response["batch_id"] == "batch-123"
    assert stored_task["external_task_id"] == "external-123"
    assert stored_task["batch_id"] == "batch-123"
    assert stored_task["callback"] == robyn_app._make_callback_state("https://example.com/callback")
    assert stored_task["started_at"] is None
    assert stored_task["completed_at"] is None


def test_create_task_accepts_file_only_multipart_without_metadata(monkeypatch, tmp_path):
    future = StubFuture()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "tasks" / "file-only-task" / "output"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    monkeypatch.setattr(robyn_app, "_TASKS", {})
    monkeypatch.setattr(
        robyn_app,
        "_prepare_task_input",
        lambda request: (input_dir, output_dir, "upload.pdf"),
    )
    monkeypatch.setattr(robyn_app._EXECUTOR, "submit", lambda *args, **kwargs: future)

    response = robyn_app.create_task(
        DummyRequest(
            body=b"------WebKitFormBoundary\r\nfile-bytes",
            files={"file": b"pdf-bytes"},
            json_error=ValueError("not json"),
        )
    )

    task_id = response["task_id"]
    stored_task = robyn_app._TASKS[task_id]
    assert response["status"] == "queued"
    assert response["external_task_id"] is None
    assert response["batch_id"] is None
    assert stored_task["callback"] == robyn_app._make_callback_state(None)


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
    assert task["updated_at"] == task["completed_at"]
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
    assert task["updated_at"] == task["completed_at"]
    assert task["error"] == "boom"
    payload = robyn_app._terminal_task_payload(task)
    assert payload["status"] == "failed"
    assert payload["result"] is None
    assert payload["error"] == "boom"


def test_complete_task_delivers_callback_after_releasing_task_lock(monkeypatch):
    delivered = []
    robyn_app._TASKS.clear()
    robyn_app._TASKS["task-3"] = {
        "task_id": "task-3",
        "status": "queued",
        "created_at": "created",
        "updated_at": "created",
        "started_at": None,
        "completed_at": None,
        "output_dir": "service_data/tasks/task-3/output",
        "callback": robyn_app._make_callback_state("https://example.com/callback"),
        "result": None,
        "error": None,
    }

    def deliver(task):
        assert robyn_app._TASK_LOCK.acquire(blocking=False)
        robyn_app._TASK_LOCK.release()
        delivered.append(task["task_id"])

    monkeypatch.setattr(robyn_app, "_deliver_callback", deliver)

    robyn_app._complete_task("task-3", CompletedFuture(result=FakeRunResult()))

    assert delivered == ["task-3"]


def _callback_task(callback_url="https://example.com/callback"):
    return {
        "task_id": "task-callback",
        "status": "completed",
        "created_at": "created",
        "updated_at": "updated",
        "started_at": None,
        "completed_at": "completed",
        "external_task_id": "external-123",
        "batch_id": "batch-123",
        "output_dir": "service_data/tasks/task-callback/output",
        "callback": robyn_app._make_callback_state(callback_url),
        "result": {"count": 1, "results": [{"file_id": "checked.png"}]},
        "error": None,
        "future": object(),
    }


def test_deliver_callback_leaves_disabled_callback_unchanged():
    task = _callback_task(callback_url=None)
    callback_before = dict(task["callback"])
    posted = []

    robyn_app._deliver_callback(task, post_callback=lambda url, payload: posted.append((url, payload)))

    assert task["callback"] == callback_before
    assert posted == []


def test_deliver_callback_marks_delivered_after_success_with_injected_post():
    task = _callback_task()
    posts = []

    def fake_post(url, payload):
        posts.append((url, payload))

    robyn_app._deliver_callback(task, post_callback=fake_post)

    assert len(posts) == 1
    assert posts[0][0] == "https://example.com/callback"
    sent_payload = posts[0][1]
    assert sent_payload["task_id"] == "task-callback"
    assert sent_payload["callback"] is not task["callback"]
    assert sent_payload["callback"]["status"] == "pending"
    assert sent_payload["callback"]["attempts"] == 1
    assert sent_payload["callback"]["last_error"] is None
    assert sent_payload["callback"]["last_attempt_at"] is not None
    assert task["callback"]["status"] == "delivered"
    assert task["callback"]["attempts"] == 1
    assert task["callback"]["last_error"] is None
    assert task["callback"]["last_attempt_at"] is not None


def test_deliver_callback_marks_failed_after_retries_with_attempts_and_last_error():
    task = _callback_task()
    attempts = []

    def failing_post(url, payload):
        attempts.append((url, payload))
        raise RuntimeError(f"network down {len(attempts)}")

    robyn_app._deliver_callback(task, post_callback=failing_post, max_attempts=3)

    assert len(attempts) == 3
    assert {url for url, _payload in attempts} == {"https://example.com/callback"}
    assert [payload["callback"]["attempts"] for _url, payload in attempts] == [1, 2, 3]
    assert [payload["callback"]["last_error"] for _url, payload in attempts] == [None, "network down 1", "network down 2"]
    assert task["callback"]["status"] == "failed"
    assert task["callback"]["attempts"] == 3
    assert task["callback"]["last_error"] == "network down 3"
    assert task["callback"]["last_attempt_at"] is not None


def test_deliver_callback_posts_independent_payload_snapshots():
    task = _callback_task()
    posted_payloads = []

    def failing_post(_url, payload):
        posted_payloads.append(payload)
        raise RuntimeError("HTTP 500")

    robyn_app._deliver_callback(task, post_callback=failing_post, max_attempts=2)

    first_payload = posted_payloads[0]
    second_payload = posted_payloads[1]
    assert first_payload is not second_payload
    assert first_payload["callback"] is not task["callback"]
    assert first_payload["callback"]["attempts"] == 1
    assert first_payload["callback"]["last_error"] is None
    assert second_payload["callback"]["attempts"] == 2
    assert second_payload["callback"]["last_error"] == "HTTP 500"


def test_health_response_remains_compatible():
    response = robyn_app.health()

    assert response["status"] == "ok"
    assert response["service"] == "omrchecker-robyn"
    assert "workers" in response
    assert "template_dir" in response


def test_robyn_internal_worker_config_matches_service_workers():
    assert robyn_app.app.config.workers == robyn_app._MAX_WORKERS


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
