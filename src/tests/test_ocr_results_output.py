from pathlib import Path

import pandas as pd

from src.entry import append_ocr_result_rows
from src.utils.file import OCR_RESULTS_COLUMNS, append_ocr_results_csv


def test_append_ocr_results_csv_does_not_create_file_for_empty_rows(tmp_path: Path) -> None:
    result = append_ocr_results_csv(tmp_path, [])

    assert result is None
    assert not (tmp_path / "OcrResults.csv").exists()


def test_append_ocr_results_csv_writes_header_and_serializes_bbox(tmp_path: Path) -> None:
    csv_path = append_ocr_results_csv(
        tmp_path,
        [
            {
                "file_id": "sheet-1.png",
                "input_path": "input/sheet-1.png",
                "output_path": "output/CheckedOMRs/sheet-1.png",
                "field": "blankScore1",
                "value": "5",
                "confidence": 0.982,
                "engine": "paddleocr",
                "regionCode": "blankScore",
                "regionName": "填空题得分区域",
                "type": "BLANK_SCORE",
                "bbox": {"x": 120, "y": 80, "width": 160, "height": 60},
                "artifactLocalPath": "artifacts/sheet-1/blankScore1.png",
            }
        ],
    )

    assert csv_path == tmp_path / "OcrResults.csv"
    rows = pd.read_csv(csv_path, dtype=str)
    assert list(rows.columns) == OCR_RESULTS_COLUMNS
    assert rows.to_dict("records") == [
        {
            "file_id": "sheet-1.png",
            "input_path": "input/sheet-1.png",
            "output_path": "output/CheckedOMRs/sheet-1.png",
            "field": "blankScore1",
            "value": "5",
            "confidence": "0.982",
            "engine": "paddleocr",
            "regionCode": "blankScore",
            "regionName": "填空题得分区域",
            "type": "BLANK_SCORE",
            "bbox": '{"height": 60, "width": 160, "x": 120, "y": 80}',
            "artifactLocalPath": "artifacts/sheet-1/blankScore1.png",
        }
    ]


def test_append_ocr_results_csv_appends_multiple_images_to_same_file(tmp_path: Path) -> None:
    append_ocr_results_csv(
        tmp_path,
        [
            {
                "file_id": "sheet-1.png",
                "field": "blankScore1",
                "value": "5",
                "confidence": 0.9,
                "bbox": [10, 20, 30, 15],
            }
        ],
    )
    append_ocr_results_csv(
        tmp_path,
        [
            {
                "file_id": "sheet-2.png",
                "field": "blankScore1",
                "value": "6",
                "confidence": 0.8,
                "bbox": [10, 20, 30, 15],
            }
        ],
    )

    rows = pd.read_csv(tmp_path / "OcrResults.csv", dtype=str).to_dict("records")
    assert [row["file_id"] for row in rows] == ["sheet-1.png", "sheet-2.png"]
    assert [row["bbox"] for row in rows] == ["[10, 20, 30, 15]", "[10, 20, 30, 15]"]


def test_append_ocr_result_rows_writes_last_ocr_results_with_paths(tmp_path: Path) -> None:
    class Paths:
        results_dir = tmp_path

    append_ocr_result_rows(
        "sheet-1.png",
        Path("input/sheet-1.png"),
        Path("output/CheckedOMRs/sheet-1.png"),
        {
            "blankScore1": {
                "text": "5",
                "confidence": 0.91,
                "engine": "paddleocr",
                "regionCode": "blankScore",
                "regionName": "填空题得分区域",
                "type": "BLANK_SCORE",
                "bbox": [10, 20, 30, 15],
            }
        },
        Paths(),
    )

    rows = pd.read_csv(tmp_path / "OcrResults.csv", dtype=str).to_dict("records")
    assert rows[0]["input_path"] == "input/sheet-1.png"
    assert rows[0]["output_path"] == "output/CheckedOMRs/sheet-1.png"
    assert rows[0]["field"] == "blankScore1"
    assert rows[0]["value"] == "5"
    assert rows[0]["engine"] == "paddleocr"
