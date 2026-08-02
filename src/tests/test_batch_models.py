import re

import pytest

from src.services.batch_models import (
    ArtifactPayload,
    BatchRecognitionRequest,
    BatchRecognitionResult,
    SheetRecognitionResult,
    render_callback_payload_from_records,
)


def test_batch_request_parses_camel_case_and_serializes_api_payload():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "externalBatchId": "external-1",
            "callbackUrl": "https://example.test/callback",
            "recognitionConfig": {"template": "standard", "flags": ["fast"]},
            "sheets": [
                {"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf", "metadata": {"page": 1}},
                {"sheetId": "sheet-2", "osskey": "inputs/sheet-2.pdf"},
            ],
        }
    )

    assert request.exam_id == "exam-1"
    assert request.external_batch_id == "external-1"
    assert request.callback_url == "https://example.test/callback"
    assert request.recognition_config == {"template": "standard", "flags": ["fast"]}
    assert request.sheets[0].sheet_id == "sheet-1"
    assert request.sheets[0].osskey == "inputs/sheet-1.pdf"
    assert request.sheets[0].metadata == {"page": 1}

    assert request.to_api_dict() == {
        "examId": "exam-1",
        "externalBatchId": "external-1",
        "callbackUrl": "https://example.test/callback",
        "recognitionConfig": {"template": "standard", "flags": ["fast"]},
        "sheets": [
            {"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf", "metadata": {"page": 1}},
            {"sheetId": "sheet-2", "osskey": "inputs/sheet-2.pdf"},
        ],
    }


def test_batch_request_defaults_recognition_config_to_empty_dict_when_omitted_or_null():
    omitted = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "callbackUrl": "https://example.test/callback",
            "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}],
        }
    )
    null_value = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "callbackUrl": "https://example.test/callback",
            "recognitionConfig": None,
            "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}],
        }
    )

    assert omitted.recognition_config == {}
    assert null_value.recognition_config == {}
    assert "externalBatchId" not in omitted.to_api_dict()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "examId is required"),
        ({"examId": "   "}, "examId must be a non-empty string"),
        ({"examId": "exam-1"}, "callbackUrl is required"),
        ({"examId": "exam-1", "callbackUrl": ""}, "callbackUrl must be a non-empty string"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback"}, "sheets is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": []}, "sheets must be a non-empty list"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{}]}, "sheets[0].sheetId is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{"sheetId": "sheet-1"}]}, "sheets[0].osskey is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": [] , "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig must be an object"),
    ],
)
def test_batch_request_validation_failures_are_clear(payload, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        BatchRecognitionRequest.from_api_json(payload)


def test_result_payload_serializes_correlation_fields_counts_and_artifacts():
    payload = BatchRecognitionResult(
        task_id="task-1",
        exam_id="exam-1",
        external_batch_id="external-1",
        status="completed",
        sheets=[
            SheetRecognitionResult(
                sheet_id="sheet-1",
                source_osskey="inputs/sheet-1.pdf",
                status="completed",
                result={"answers": ["A", "B"], "score": 2},
                artifacts=[
                    ArtifactPayload(
                        artifact_type="region_screenshot",
                        osskey="artifacts/task-1/sheet-1/region-1.png",
                        metadata={"region": "business-large"},
                    )
                ],
            ),
            SheetRecognitionResult(
                sheet_id="sheet-2",
                source_osskey="inputs/sheet-2.pdf",
                status="failed",
                result=[],
                artifacts=[],
                error="unreadable",
            ),
        ],
    )

    assert payload.aggregate_counts == {"total": 2, "completed": 1, "failed": 1}
    assert payload.to_callback_dict() == {
        "taskId": "task-1",
        "examId": "exam-1",
        "externalBatchId": "external-1",
        "status": "completed",
        "aggregateCounts": {"total": 2, "completed": 1, "failed": 1},
        "sheets": [
            {
                "sheetId": "sheet-1",
                "sourceOsskey": "inputs/sheet-1.pdf",
                "status": "completed",
                "result": {"answers": ["A", "B"], "score": 2},
                "artifacts": [
                    {
                        "artifactType": "region_screenshot",
                        "osskey": "artifacts/task-1/sheet-1/region-1.png",
                        "metadata": {"region": "business-large"},
                    }
                ],
            },
            {
                "sheetId": "sheet-2",
                "sourceOsskey": "inputs/sheet-2.pdf",
                "status": "failed",
                "result": [],
                "artifacts": [],
                "error": "unreadable",
            },
        ],
    }


def test_render_callback_payload_from_task_store_like_records_groups_sheet_artifacts():
    payload = render_callback_payload_from_records(
        batch={
            "task_id": "task-1",
            "exam_id": "exam-1",
            "external_batch_id": "external-1",
            "status": "completed",
            "error": None,
        },
        sheets=[
            {
                "sheet_id": "sheet-1",
                "source_osskey": "inputs/sheet-1.pdf",
                "status": "completed",
                "result_json": {"answers": ["C"]},
                "error": None,
            }
        ],
        artifacts=[
            {
                "sheet_id": "sheet-1",
                "artifact_type": "marked_image",
                "osskey": "artifacts/task-1/sheet-1/marked.png",
                "metadata_json": {"width": 1200},
            },
            {
                "sheet_id": None,
                "artifact_type": "summary",
                "osskey": "artifacts/task-1/summary.json",
            },
        ],
    )

    assert payload["examId"] == "exam-1"
    assert payload["externalBatchId"] == "external-1"
    assert payload["sheets"][0]["sheetId"] == "sheet-1"
    assert payload["sheets"][0]["sourceOsskey"] == "inputs/sheet-1.pdf"
    assert payload["sheets"][0]["artifacts"] == [
        {
            "artifactType": "marked_image",
            "osskey": "artifacts/task-1/sheet-1/marked.png",
            "metadata": {"width": 1200},
        }
    ]
    assert payload["artifacts"] == [
        {"artifactType": "summary", "osskey": "artifacts/task-1/summary.json"}
    ]
