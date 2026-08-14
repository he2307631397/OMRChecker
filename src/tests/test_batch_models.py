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
            "templateCode": "ASTS-HTTP-001",
            "schemaVersion": "v1",
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
    assert request.template_code == "ASTS-HTTP-001"
    assert request.schema_version == "v1"
    assert request.callback_url == "https://example.test/callback"
    assert request.recognition_config == {"template": {"name": "standard"}, "flags": ["fast"]}
    assert request.sheets[0].sheet_id == "sheet-1"
    assert request.sheets[0].osskey == "inputs/sheet-1.pdf"
    assert request.sheets[0].metadata == {"page": 1}

    assert request.to_api_dict() == {
        "examId": "exam-1",
        "externalBatchId": "external-1",
        "templateCode": "ASTS-HTTP-001",
        "schemaVersion": "v1",
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


def test_batch_request_accepts_dynamic_archive_regions():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-1",
            "recognitionConfig": {
                "regions": {
                    "archiveRegions": [
                        {"regionCode": "blankScore", "regionName": "填空题得分区域", "type": "BLANK_SCORE", "bbox": [10, 20, 30, 40]}
                    ]
                }
            },
            "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}],
        }
    )

    assert request.recognition_config["regions"]["archiveRegions"][0]["regionCode"] == "blankScore"


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
        ({"examId": "exam-1", "templateCode": "../ASTS"}, "templateCode must be a safe template path component like ASTS-HTTP-001"),
        ({"examId": "exam-1", "schemaVersion": "v1"}, "templateCode is required when schemaVersion is supplied"),
        ({"examId": "exam-1", "templateVersion": "../v1"}, "templateVersion must be a safe template path component like v1"),
        ({"examId": "exam-1"}, "sheets is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": []}, "sheets must be a non-empty list"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{}]}, "sheets[0].sheetId is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "sheets": [{"sheetId": "sheet-1"}]}, "sheets[0].osskey is required"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": [] , "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig must be an object"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": {"template": "standard"}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.template must be an object"),
        ({"examId": "exam-1", "callbackUrl": "https://example.test/callback", "recognitionConfig": {"config": []}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.config must be an object"),
        ({"examId": "exam-1", "recognitionConfig": {"regions": "bad"}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.regions must be a list or an object with archiveRegions"),
        ({"examId": "exam-1", "recognitionConfig": {"archiveRegions": [{"regionCode": "blank", "regionName": "填空", "type": "BLANK", "bbox": [1, 2, 0, 4]}]}, "sheets": [{"sheetId": "sheet-1", "osskey": "inputs/sheet-1.pdf"}]}, "recognitionConfig.archiveRegions[0].bbox width and height must be positive"),
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
                        artifact_type="businessLarge",
                        osskey="artifacts/task-1/sheet-1/region-1.png",
                        metadata={"regionCode": "businessLarge", "regionName": "大题区域"},
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
                "answers": ["A", "B"],
                "score": 2,
            },
            {
                "sheetId": "sheet-2",
                "sourceOsskey": "inputs/sheet-2.pdf",
                "status": "failed",
                "error": "unreadable",
            },
        ],
    }


def test_result_payload_keeps_ocr_engine_on_region_not_items():
    payload = BatchRecognitionResult(
        task_id="task-ocr",
        exam_id="exam-1",
        status="completed",
        sheets=[
            SheetRecognitionResult(
                sheet_id="sheet-1",
                source_osskey="inputs/sheet-1.pdf",
                status="completed",
                result={
                    "file_id": "sheet-1.png",
                    "answers": [
                        {
                            "regionCode": "blankScore",
                            "regionName": "填空题得分区域",
                            "type": "BLANK_SCORE",
                            "engine": "paddleocr",
                            "items": [
                                {
                                    "field": "fill_blank_score_text",
                                    "value": "15",
                                    "confidence": 0.999,
                                    "artifactLocalPath": "artifacts/sheet-1/fill.png",
                                }
                            ],
                        }
                    ],
                    "answers_flat": {"fill_blank_score_text": "15"},
                },
            )
        ],
    )

    sheet = payload.to_callback_dict()["sheets"][0]
    region = sheet["answers"][0]

    assert region["engine"] == "ocr"
    assert "engine" not in region["items"][0]
    assert sheet["fileId"] == "sheet-1.png"
    assert "file_id" not in sheet
    assert "answers_flat" not in sheet


def test_result_payload_compacts_business_answers_and_attaches_region_osskeys():
    payload = BatchRecognitionResult(
        task_id="task-ocr",
        exam_id="exam-1",
        status="completed",
        sheets=[
            SheetRecognitionResult(
                sheet_id="sheet-1",
                source_osskey="inputs/sheet-1.pdf",
                status="completed",
                result={
                    "score": "15",
                    "checkedImageOsskey": "checked/task-ocr/sheet-1.png",
                    "file_id": "sheet-1.png",
                    "exam_id": "27423564",
                    "review_required": True,
                    "weak_marks": [],
                    "answers": [
                        {
                            "regionCode": "fillBlank",
                            "regionName": "填空题",
                            "type": "FILL_BLANK",
                            "engine": "paddleocr",
                            "items": [
                                {
                                    "field": "score",
                                    "value": "15",
                                    "confidence": 0.999,
                                    "artifactLocalPath": "local.png",
                                }
                            ],
                        }
                    ],
                    "answers_flat": {"score": "15"},
                    "input_path": "local-input.png",
                    "output_path": "local-output.png",
                },
                artifacts=[
                    ArtifactPayload(
                        artifact_type="fillBlank",
                        osskey="artifacts/task-ocr/sheet-1/fill.png",
                        metadata={"regionCode": "fillBlank", "bbox": {"x": 1}},
                    )
                ],
            )
        ],
    )

    sheet = payload.to_callback_dict()["sheets"][0]

    assert sheet == {
        "sheetId": "sheet-1",
        "sourceOsskey": "inputs/sheet-1.pdf",
        "status": "completed",
        "score": "15",
        "checkedImageOsskey": "checked/task-ocr/sheet-1.png",
        "examNo": "27423564",
        "fileId": "sheet-1.png",
        "review_required": True,
        "weak_marks": [],
        "answers": [
            {
                "engine": "ocr",
                "type": "FILL_BLANK",
                "regionCode": "fillBlank",
                "regionName": "填空题",
                "osskey": "artifacts/task-ocr/sheet-1/fill.png",
                "items": [{"field": "score", "value": "15", "confidence": 0.999}],
            }
        ],
    }


def test_result_payload_attaches_osskeys_using_business_region_aliases():
    payload = BatchRecognitionResult(
        task_id="task-alias",
        exam_id="exam-1",
        status="completed",
        sheets=[
            SheetRecognitionResult(
                sheet_id="sheet-1",
                source_osskey="inputs/sheet-1.pdf",
                status="completed",
                result={
                    "answers": [
                        {"engine": "omr", "type": "MULTIPLE_CHOICE", "regionCode": "multipleChoice", "regionName": "多选题区域", "items": []},
                        {"engine": "ocr", "type": "FILL_BLANK", "regionCode": "fillBank", "regionName": "填空题", "items": []},
                        {"engine": "ocr", "type": "SOLUTION", "regionCode": "solution", "regionName": "解答题", "items": []},
                    ],
                },
                artifacts=[
                    ArtifactPayload(
                        artifact_type="multiChoice",
                        osskey="artifacts/task-alias/sheet-1/multi.png",
                        metadata={"regionCode": "multiChoice", "regionName": "多选题区域", "regionType": "MULTI_CHOICE"},
                    ),
                    ArtifactPayload(
                        artifact_type="FillBlankReview",
                        osskey="artifacts/task-alias/sheet-1/fill.png",
                        metadata={"regionCode": "FillBlankReview", "regionName": "填空题人工审核区域", "regionType": "FILL_BLANK_REVIEW"},
                    ),
                    ArtifactPayload(
                        artifact_type="SolutionQ14Review",
                        osskey="artifacts/task-alias/sheet-1/solution.png",
                        metadata={"regionCode": "SolutionQ14Review", "regionName": "第14题解答题人工审核区域", "regionType": "SOLUTION_REVIEW"},
                    ),
                ],
            )
        ],
    )

    answers = payload.to_callback_dict()["sheets"][0]["answers"]

    assert [answer["osskey"] for answer in answers] == [
        "artifacts/task-alias/sheet-1/multi.png",
        "artifacts/task-alias/sheet-1/fill.png",
        "artifacts/task-alias/sheet-1/solution.png",
    ]


def test_result_payload_prefers_largest_review_region_over_small_ocr_crops():
    payload = BatchRecognitionResult(
        task_id="task-largest",
        exam_id="exam-1",
        status="completed",
        sheets=[
            SheetRecognitionResult(
                sheet_id="sheet-1",
                source_osskey="inputs/sheet-1.pdf",
                status="completed",
                result={
                    "answers": [
                        {"engine": "ocr", "type": "FILL_BLANK", "regionCode": "fillBank", "regionName": "填空题", "items": []},
                        {"engine": "ocr", "type": "SOLUTION", "regionCode": "solution", "regionName": "解答题", "items": []},
                    ],
                },
                artifacts=[
                    ArtifactPayload(
                        artifact_type="FillBlank",
                        osskey="artifacts/task-largest/sheet-1/fill-score-small.png",
                        metadata={"regionCode": "FillBlank", "regionName": "填空题", "regionType": "score", "bbox": {"width": 95, "height": 60}},
                    ),
                    ArtifactPayload(
                        artifact_type="FillBlankReview",
                        osskey="artifacts/task-largest/sheet-1/fill-review-large.png",
                        metadata={"regionCode": "FillBlankReview", "regionName": "填空题人工审核区域", "regionType": "FILL_BLANK_REVIEW", "bbox": {"width": 1050, "height": 160}},
                    ),
                    ArtifactPayload(
                        artifact_type="Q14",
                        osskey="artifacts/task-largest/sheet-1/solution-score-small.png",
                        metadata={"regionCode": "Q14", "regionName": "第14题解答题", "regionType": "score", "bbox": {"width": 95, "height": 65}},
                    ),
                    ArtifactPayload(
                        artifact_type="SolutionQ14Review",
                        osskey="artifacts/task-largest/sheet-1/solution-review-large.png",
                        metadata={"regionCode": "SolutionQ14Review", "regionName": "第14题解答题人工审核区域", "regionType": "SOLUTION_REVIEW", "bbox": {"width": 1050, "height": 445}},
                    ),
                ],
            )
        ],
    )

    answers = payload.to_callback_dict()["sheets"][0]["answers"]

    assert [answer["osskey"] for answer in answers] == [
        "artifacts/task-largest/sheet-1/fill-review-large.png",
        "artifacts/task-largest/sheet-1/solution-review-large.png",
    ]


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
    assert "artifacts" not in payload["sheets"][0]
    assert "artifacts" not in payload


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
