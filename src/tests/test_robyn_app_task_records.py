import pytest

from web.robyn_app import _extract_request_metadata, _make_callback_state


class DummyRequest:
    def __init__(self, body=None, json_payload=None, form_data=None, form=None):
        self.body = body
        self._json_payload = json_payload
        if form_data is not None:
            self.form_data = form_data
        if form is not None:
            self.form = form

    def json(self):
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
