from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.services.region_artifacts import RegionSpec, generate_region_artifacts
from src.services.service_config import ArchiveRegionConfig


def _write_synthetic_image(path: Path) -> None:
    image = np.zeros((80, 120, 3), dtype=np.uint8)
    image[10:30, 5:45] = (0, 0, 255)
    image[40:70, 60:110] = (0, 255, 0)
    assert cv2.imwrite(str(path), image)


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

    assert [artifact.artifact_type for artifact in artifacts] == ["region_screenshot", "region_screenshot"]
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

    first_crop = cv2.imread(artifacts[0].metadata["localPath"])
    second_crop = cv2.imread(artifacts[1].metadata["localPath"])
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
    assert Path(first.metadata["localPath"]).name == "sheet_A_single_choice_单选题_区域.png"
