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
            "templateVersion": "v1",
            "callbackUrl": "https://example.test/callback",
            "recognitionConfig": {"template": {"name": "standard"}, "flags": ["fast"]},
            "sheets": [
                {"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf", "metadata": {"page": 1}},
                {"sheetId": "sheet-2", "osskey": "inputs/sheet-2.pdf"},
            ],
        }
    )

    assert request.exam_id == "exam-1"
    assert request.external_batch_id == "external-1"
    assert request.template_version == "v1"
    assert request.callback_url == "https://example.test/callback"
    assert request.recognition_config == {"template": {"name": "standard"}, "flags": ["fast"]}
    assert request.sheets[0].sheet_id == "sheet-1"
    assert request.sheets[0].osskey == "inputs/sheet-1.pdf"
    assert request.sheets[0].metadata == {"page": 1}

    assert request.to_api_dict() == {
        "examId": "exam-1",
        "externalBatchId": "external-1",
        "templateVersion": "v1",
        "callbackUrl": "https://example.test/callback",
        "recognitionConfig": {"template": {"name": "standard"}, "flags": ["fast"]},
        "sheets": [
            {"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf", "metadata": {"page": 1}},
            {"sheetId": "sheet-2", "osskey": "inputs/sheet-2.pdf"},
        ],
    }


def test_batch_request_defaults_recognition_config_to_empty_dict_when_omitted_or_null():
    omitted = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
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
    assert "callbackUrl" not in omitted.to_api_dict()


def test_batch_request_accepts_integer_business_ids_from_complete_payload():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": 17,
            "templateSpecId": 1,
            "externalBatchId": "scan_batch_file:1785991732373",
            "attemptNo": 1785991732373,
            "batchId": 1,
            "recognitionConfig": {"config": {}, "templateConfig": {}},
            "sheets": [{"sheetId": 1, "osskey": "private/exam/sheet-1.pdf"}],
        }
    )

    assert request.exam_id == "17"
    assert request.callback_url is None
    assert request.sheets[0].sheet_id == "1"
    assert request.recognition_config == {"config": {}, "templateConfig": {}}
    assert request.extra_fields == {"templateSpecId": 1, "attemptNo": 1785991732373, "batchId": 1}
    assert request.to_api_dict()["templateSpecId"] == 1


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "examId is required"),
        ({"examId": "   "}, "examId must be a non-empty string"),
        ({"examId": "exam-1", "callbackUrl": ""}, "callbackUrl must be a non-empty string"),
        ({"examId": "exam-1", "templateVersion": "../v1"}, "templateVersion must be a safe template version like v1"),
        ({"examId": "exam-1"}, "sheets is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": []}, "sheets must be a non-empty list"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{}]}, "sheets[0].sheetId is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{"sheetId": "sheet-1"}]}, "sheets[0].osskey is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": [] , "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig must be an object"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": {"template": "standard"}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.template must be an object"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": {"config": []}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.config must be an object"),
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
                "osskey": "inputs/sheet-1.pdf",
                "sourceOsskey": "inputs/sheet-1.pdf",
                "status": "completed",
                "answers": ["A", "B"],
                "score": 2,
                "result": {"answers": ["A", "B"], "score": 2},
                "artifacts": [
                    {
                        "artifactType": "region_screenshot",
                        "osskey": "artifacts/task-1/sheet-1/region-1.png",
                        "metadata": {"region": "business-large"},
                    }
                ],
                "regionImages": [
                    {
                        "osskey": "artifacts/task-1/sheet-1/region-1.png",
                        "uploadStatus": "uploaded",
                    }
                ],
            },
            {
                "sheetId": "sheet-2",
                "osskey": "inputs/sheet-2.pdf",
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


def test_batch_request_debug_artifacts_override_parses_true():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "callbackUrl": "https://example.test/callback",
            "recognitionConfig": {"debugArtifacts": True},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is True
    assert request.to_api_dict()["recognitionConfig"]["debugArtifacts"] is True


def test_batch_request_debug_artifacts_override_parses_false():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "callbackUrl": "https://example.test/callback",
            "recognitionConfig": {"debugArtifacts": False},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is False
    assert request.to_api_dict()["recognitionConfig"]["debugArtifacts"] is False


def test_batch_request_omits_recognition_config_when_no_override():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "callbackUrl": "https://example.test/callback",
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is None
    assert request.to_api_dict()["recognitionConfig"] == {}


def test_batch_request_rejects_non_boolean_debug_artifacts():
    with pytest.raises(ValueError, match="recognitionConfig.debugArtifacts"):
        BatchRecognitionRequest.from_api_json(
            {
                "examId": "exam-001",
                "callbackUrl": "https://example.test/callback",
                "recognitionConfig": {"debugArtifacts": "true"},
                "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
            }
        )
