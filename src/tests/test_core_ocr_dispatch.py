from pathlib import Path

import numpy as np
import pytest

from src.core import ImageInstanceOps
from src.defaults.config import CONFIG_DEFAULTS
from src.ocr.engine import OcrResult
from src.ocr.region import crop_ocr_region
from src.template import Template


class FakeOcrEngine:
    def __init__(self, result: OcrResult | None = None) -> None:
        self.result = result or OcrResult(text="5", confidence=0.91, raw={"fake": True})
        self.calls = []

    def recognize(self, image, options=None):
        self.calls.append((image.copy(), dict(options or {})))
        return self.result


def _write_template(path: Path, field_blocks: str, output_columns: str) -> None:
    path.write_text(
        f"""
        {{
          "pageDimensions": [200, 120],
          "bubbleDimensions": [10, 10],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {field_blocks},
          "outputColumns": {output_columns},
          "customLabels": {{}}
        }}
        """,
        encoding="utf-8",
    )


def _ocr_template(tmp_path: Path) -> Template:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "blank_score_1": {
            "engine": "paddleocr",
            "fieldLabels": ["blankScore1"],
            "origin": [10, 20],
            "dimensions": [30, 15],
            "ocr": {"lang": "en", "det": false, "cls": false}
          }
        }
        """,
        '["blankScore1"]',
    )
    return Template(template_path, CONFIG_DEFAULTS)


def _omr_template(tmp_path: Path) -> Template:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldType": "QTYPE_MCQ4",
            "fieldLabels": ["q1"],
            "origin": [10, 20],
            "bubblesGap": 20,
            "labelsGap": 20
          }
        }
        """,
        '["q1"]',
    )
    return Template(template_path, CONFIG_DEFAULTS)


def test_crop_ocr_region_returns_copy_with_expected_dimensions(tmp_path: Path) -> None:
    template = _ocr_template(tmp_path)
    image = np.arange(120 * 200, dtype=np.uint8).reshape((120, 200))

    crop = crop_ocr_region(image, template.field_blocks[0])

    assert crop.shape == (15, 30)
    assert np.array_equal(crop, image[20:35, 10:40])
    crop[:, :] = 0
    assert not np.array_equal(crop, image[20:35, 10:40])


def test_crop_ocr_region_rejects_out_of_bounds_block(tmp_path: Path) -> None:
    template = _ocr_template(tmp_path)
    block = template.field_blocks[0]
    block.origin = [190, 110]

    with pytest.raises(ValueError, match="blank_score_1.*outside image bounds"):
        crop_ocr_region(np.zeros((120, 200), dtype=np.uint8), block)


def test_read_omr_response_dispatches_paddleocr_block(tmp_path: Path) -> None:
    template = _ocr_template(tmp_path)
    image = np.full((120, 200), 255, dtype=np.uint8)
    image[20:35, 10:40] = 17
    fake_ocr = FakeOcrEngine()
    ops = ImageInstanceOps(CONFIG_DEFAULTS, ocr_engine=fake_ocr)

    response, final_marked, multi_marked, multi_roll = ops.read_omr_response(
        template, image, "sample.png"
    )

    assert response == {"blankScore1": "5"}
    assert final_marked.shape == image.shape
    assert multi_marked is False
    assert multi_roll is False
    assert len(fake_ocr.calls) == 1
    called_image, called_options = fake_ocr.calls[0]
    assert called_image.shape == (15, 30)
    assert np.all(called_image == 0)
    assert called_options["lang"] == "en"
    assert called_options["det"] is False
    assert called_options["cls"] is False
    assert ops.last_ocr_results == {
        "blankScore1": {
            "text": "5",
            "confidence": 0.91,
            "engine": "paddleocr",
            "blockName": "blank_score_1",
            "bbox": [10, 20, 30, 15],
            "regionCode": "blank_score_1",
            "regionName": "blank_score_1",
            "type": "OCR",
        }
    }


def test_read_omr_response_normalizes_digits_only_ocr_text(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "blank_score_1": {
            "engine": "paddleocr",
            "fieldLabels": ["blankScore1"],
            "origin": [10, 20],
            "dimensions": [30, 15],
            "ocr": {"lang": "en", "digitsOnly": true}
          }
        }
        """,
        '["blankScore1"]',
    )
    template = Template(template_path, CONFIG_DEFAULTS)
    fake_ocr = FakeOcrEngine(OcrResult(text=":/O分", confidence=0.72))
    ops = ImageInstanceOps(CONFIG_DEFAULTS, ocr_engine=fake_ocr)

    response, *_ = ops.read_omr_response(template, np.full((120, 200), 255, dtype=np.uint8), "sample.png")

    assert response["blankScore1"] == "10"
    assert ops.last_ocr_results["blankScore1"]["text"] == "10"


def test_read_omr_response_does_not_call_ocr_engine_for_pure_omr_template(
    tmp_path: Path,
) -> None:
    template = _omr_template(tmp_path)
    image = np.full((120, 200), 255, dtype=np.uint8)
    fake_ocr = FakeOcrEngine()
    ops = ImageInstanceOps(CONFIG_DEFAULTS, ocr_engine=fake_ocr)

    ops.read_omr_response(template, image, "sample.png")

    assert fake_ocr.calls == []
    assert ops.last_ocr_results == {}
