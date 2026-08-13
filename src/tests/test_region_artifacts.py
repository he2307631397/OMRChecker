from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.services.region_artifacts import RegionSpec, derive_archive_regions_from_template, generate_region_artifacts, load_template_archive_regions
from src.services.service_config import ArchiveRegionConfig


def _write_synthetic_image(path: Path) -> None:
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    image[10:30, 5:45] = (0, 0, 255)
    image[40:70, 60:110] = (0, 255, 0)
    assert cv2.imwrite(str(path), image)


def _read_image(path: str | Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)


def test_crops_two_configured_large_regions_and_returns_metadata(tmp_path: Path) -> None:
    image_path = tmp_path / "aligned.png"
    _write_synthetic_image(image_path)

    regions = [
        ArchiveRegionConfig(region_code="exam_no", region_name="准考证号区域", type="student_id", bbox=[5, 10, 40, 20]),
        RegionSpec(region_code="single_choice", region_name="单选题 区域", type="single_choice", bbox=[60, 40, 50, 30]),
    ]

    artifacts = generate_region_artifacts(
        image_path,
        regions,
        tmp_path / "artifacts",
        sheet_id="sheet-1",
        task_id="task-1",
    )

    assert [artifact.artifact_type for artifact in artifacts] == ["exam_no", "single_choice"]
    assert Path(artifacts[0].metadata["localPath"]).exists()
    assert artifacts[0].metadata == {
        "localPath": artifacts[0].metadata["localPath"],
        "regionCode": "exam_no",
        "regionName": "准考证号区域",
        "regionType": "student_id",
        "bbox": {"x": 5, "y": 10, "width": 40, "height": 20},
        "sheetId": "sheet-1",
        "taskId": "task-1",
    }
    assert artifacts[1].metadata["regionName"] == "单选题 区域"
    assert artifacts[1].metadata["bbox"] == {"x": 60, "y": 40, "width": 50, "height": 30}

    first_crop = _read_image(artifacts[0].metadata["localPath"])
    second_crop = _read_image(artifacts[1].metadata["localPath"])
    assert first_crop.shape[:2] == (20, 40)
    assert second_crop.shape[:2] == (30, 50)
    assert np.all(first_crop == (0, 0, 255))
    assert np.all(second_crop == (0, 255, 0))


def test_empty_regions_return_empty_list_and_create_no_files(tmp_path: Path) -> None:
    image_path = tmp_path / "aligned.png"
    _write_synthetic_image(image_path)
    output_dir = tmp_path / "artifacts"

    assert generate_region_artifacts(image_path, [], output_dir) == []
    assert not output_dir.exists()


def test_out_of_bounds_bbox_raises_clear_value_error(tmp_path: Path) -> None:
    image_path = tmp_path / "aligned.png"
    _write_synthetic_image(image_path)

    with pytest.raises(ValueError, match="bbox.*outside image bounds.*too_wide"):
        generate_region_artifacts(
            image_path,
            [RegionSpec(region_code="too_wide", region_name="越界区域", type="single_choice", bbox=[100, 10, 30, 20])],
            tmp_path / "artifacts",
        )


def test_filename_sanitization_is_deterministic_for_chinese_and_spaces(tmp_path: Path) -> None:
    image_path = tmp_path / "aligned.png"
    _write_synthetic_image(image_path)
    region = RegionSpec(region_code="single choice", region_name="单选题 区域", type="single_choice", bbox=[60, 40, 50, 30])

    first = generate_region_artifacts(image_path, [region], tmp_path / "first", sheet_id="sheet A")[0]
    second = generate_region_artifacts(image_path, [region], tmp_path / "second", sheet_id="sheet A")[0]

    assert Path(first.metadata["localPath"]).name == Path(second.metadata["localPath"]).name
    assert Path(first.metadata["localPath"]).name == "001_sheet_A_single_choice_单选题_区域.png"


def test_filename_generation_keeps_sanitized_collisions_unique(tmp_path: Path) -> None:
    image_path = tmp_path / "aligned.png"
    _write_synthetic_image(image_path)
    regions = [
        RegionSpec(region_code="same code", region_name="同名 区域", type="single_choice", bbox=[5, 10, 40, 20]),
        RegionSpec(region_code="same/code", region_name="同名/区域", type="single_choice", bbox=[60, 40, 50, 30]),
    ]

    artifacts = generate_region_artifacts(image_path, regions, tmp_path / "artifacts", sheet_id="sheet A")

    paths = [Path(artifact.metadata["localPath"]) for artifact in artifacts]
    assert [path.name for path in paths] == [
        "001_sheet_A_same_code_同名_区域.png",
        "002_sheet_A_same_code_同名_区域.png",
    ]
    assert paths[0] != paths[1]
    assert np.all(_read_image(paths[0]) == (0, 0, 255))
    assert np.all(_read_image(paths[1]) == (0, 255, 0))


def test_derives_archive_regions_from_template_field_blocks(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1190, 1682],
          "bubbleDimensions": [29, 18],
          "fieldBlocks": {
            "ExamId": {"fieldType": "QTYPE_INT", "fieldLabels": ["id1..8"], "origin": [777, 396], "bubbleDimensions": [30, 17], "bubblesGap": 27, "labelsGap": 44},
            "Q1": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q1"], "origin": [134, 757], "bubblesGap": 39, "labelsGap": 0},
            "Q2": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q2"], "origin": [337, 802], "bubblesGap": 39, "labelsGap": 0},
            "Q9": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q9"], "origin": [134, 933], "bubblesGap": 39, "labelsGap": 0, "multiSelect": true}
          }
        }
        """,
        encoding="utf-8",
    )

    regions = derive_archive_regions_from_template(template_path, margin=10)

    assert [(region.region_code, region.region_name, region.type) for region in regions] == [
        ("candidateNumber", "准考证号区域", "DIGIT"),
        ("singleChoice", "单选题区域", "SINGLE_CHOICE"),
        ("multiChoice", "多选题区域", "MULTI_CHOICE"),
    ]
    assert regions[0].bbox == [468, 261, 657, 405]
    assert regions[1].bbox == [39, 690, 454, 140]
    assert regions[2].bbox == [39, 866, 251, 95]


def test_derives_paddleocr_archive_regions_from_template_field_blocks(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [29, 18],
          "fieldBlocks": {
            "blank_score_1": {
              "engine": "paddleocr",
              "fieldLabels": ["blankScore1"],
              "origin": [120, 80],
              "dimensions": [160, 60],
              "regionCode": "blankScore",
              "regionName": "填空题得分区域",
              "type": "BLANK_SCORE",
              "ocr": {"archiveRegion": true}
            },
            "solution_answer_2": {
              "engine": "paddleocr",
              "fieldLabels": ["solutionAnswer2"],
              "origin": [100, 200],
              "dimensions": [500, 220],
              "regionCode": "solutionAnswer",
              "regionName": "解答题解答区域",
              "type": "SOLUTION_ANSWER"
            },
            "internal_note": {
              "engine": "paddleocr",
              "fieldLabels": ["internalNote"],
              "origin": [10, 20],
              "dimensions": [30, 40],
              "regionCode": "internalNote",
              "regionName": "内部备注区域",
              "type": "INTERNAL_NOTE",
              "ocr": {"archiveRegion": false}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    regions = derive_archive_regions_from_template(template_path)

    assert regions == [
        RegionSpec(
            region_code="blankScore",
            region_name="填空题得分区域",
            type="BLANK_SCORE",
            bbox=[120, 80, 160, 60],
        ),
        RegionSpec(
            region_code="solutionAnswer",
            region_name="解答题解答区域",
            type="SOLUTION_ANSWER",
            bbox=[100, 200, 500, 220],
        ),
    ]


def test_derives_paddleocr_archive_regions_from_template_field_block_ocrs(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [29, 18],
          "fieldBlocks": {},
          "fieldBlockOcrs": {
            "blank_score_1": {
              "fieldLabels": ["blankScore1"],
              "origin": [120, 80],
              "dimensions": [160, 60],
              "regionCode": "blankScore",
              "regionName": "填空题得分区域",
              "type": "BLANK_SCORE",
              "ocr": {"archiveRegion": true}
            },
            "internal_note": {
              "fieldLabels": ["internalNote"],
              "origin": [10, 20],
              "dimensions": [30, 40],
              "regionCode": "internalNote",
              "regionName": "内部备注区域",
              "type": "INTERNAL_NOTE",
              "ocr": {"archiveRegion": false}
            }
          }
        }
        """,
        encoding="utf-8",
    )

    regions = derive_archive_regions_from_template(template_path)

    assert regions == [
        RegionSpec(
            region_code="blankScore",
            region_name="填空题得分区域",
            type="BLANK_SCORE",
            bbox=[120, 80, 160, 60],
        )
    ]


def test_template_regions_json_overrides_derived_regions(tmp_path: Path) -> None:
    (tmp_path / "template.json").write_text('{"fieldBlocks": {}}', encoding="utf-8")
    (tmp_path / "regions.json").write_text(
        '{"archiveRegions": [{"regionCode": "custom", "regionName": "自定义区域", "type": "CUSTOM", "bbox": [1, 2, 3, 4]}]}',
        encoding="utf-8",
    )

    regions = load_template_archive_regions(tmp_path)

    assert regions == [RegionSpec(region_code="custom", region_name="自定义区域", type="CUSTOM", bbox=[1, 2, 3, 4])]


def test_template_archive_regions_append_to_derived_omr_regions(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1190, 1682],
          "bubbleDimensions": [29, 18],
          "fieldBlocks": {
            "ExamId": {"fieldType": "QTYPE_INT", "fieldLabels": ["id1..8"], "origin": [777, 396], "bubbleDimensions": [30, 17], "bubblesGap": 27, "labelsGap": 44},
            "Q1": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q1"], "origin": [134, 757], "bubblesGap": 39, "labelsGap": 0}
          },
          "archiveRegions": [
            {"regionCode": "FillBlankReview", "regionName": "填空题人工审核区域", "type": "FILL_BLANK_REVIEW", "bbox": [65, 1015, 1050, 160]}
          ]
        }
        """,
        encoding="utf-8",
    )

    regions = derive_archive_regions_from_template(template_path, margin=10)

    assert [(region.region_code, region.region_name, region.type) for region in regions] == [
        ("candidateNumber", "准考证号区域", "DIGIT"),
        ("singleChoice", "单选题区域", "SINGLE_CHOICE"),
        ("FillBlankReview", "填空题人工审核区域", "FILL_BLANK_REVIEW"),
    ]
    assert regions[-1].bbox == [65, 1015, 1050, 160]
