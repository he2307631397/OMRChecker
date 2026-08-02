import pytest

import web.robyn_app as robyn_app
from web.robyn_app import _extract_request_metadata, _make_callback_state


class DummyRequest:
    def __init__(self, body=None, json_payload=None, form_data=None, form=None, json_error=None):
        self.body = body
        self._json_payload = json_payload
        self._json_error = json_error
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
