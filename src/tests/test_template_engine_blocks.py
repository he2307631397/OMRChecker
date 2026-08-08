from pathlib import Path

import pytest

from src.defaults.config import CONFIG_DEFAULTS
from src.template import Template


def _write_template(path: Path, field_blocks: str, output_columns: str = '[]') -> None:
    path.write_text(
        f"""
        {{
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [20, 20],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {field_blocks},
          "outputColumns": {output_columns},
          "customLabels": {{}}
        }}
        """,
        encoding="utf-8",
    )


def test_legacy_omr_block_defaults_to_omr_engine(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldType": "QTYPE_MCQ4",
            "fieldLabels": ["q1"],
            "origin": [100, 100],
            "bubblesGap": 40,
            "labelsGap": 30
          }
        }
        """,
        '["q1"]',
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    block = template.field_blocks[0]
    assert block.engine == "omr"
    assert block.parsed_field_labels == ["q1"]
    assert len(block.traverse_bubbles) == 1
    assert [bubble.field_value for bubble in block.traverse_bubbles[0]] == ["A", "B", "C", "D"]


def test_explicit_omr_engine_keeps_existing_bubble_grid(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "student_id_area": {
            "engine": "omr",
            "fieldType": "QTYPE_INT",
            "fieldLabels": ["id1"],
            "origin": [100, 100],
            "bubblesGap": 25,
            "labelsGap": 30
          }
        }
        """,
        '["id1"]',
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    block = template.field_blocks[0]
    assert block.engine == "omr"
    assert block.field_type == "QTYPE_INT"
    assert len(block.traverse_bubbles[0]) == 10


def test_paddleocr_block_parses_with_engine_dimensions_and_region_metadata(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "blank_score_1": {
            "engine": "paddleocr",
            "fieldLabels": ["blankScore1"],
            "origin": [100, 100],
            "dimensions": [160, 60],
            "regionCode": "blankScore",
            "regionName": "填空题得分区域",
            "type": "BLANK_SCORE",
            "ocr": {"lang": "ch", "archiveRegion": true}
          }
        }
        """,
        '["blankScore1"]',
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    block = template.field_blocks[0]
    assert block.engine == "paddleocr"
    assert block.parsed_field_labels == ["blankScore1"]
    assert block.origin == [100, 100]
    assert block.dimensions == [160, 60]
    assert block.region_code == "blankScore"
    assert block.region_name == "填空题得分区域"
    assert block.region_type == "BLANK_SCORE"
    assert block.ocr_options == {
        "returnConfidence": True,
        "archiveRegion": True,
        "lang": "ch",
    }
    assert block.traverse_bubbles == []


def test_paddleocr_block_requires_dimensions(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "blank_score_1": {
            "engine": "paddleocr",
            "fieldLabels": ["blankScore1"],
            "origin": [100, 100]
          }
        }
        """,
        '["blankScore1"]',
    )

    with pytest.raises(Exception):
        Template(template_path, CONFIG_DEFAULTS)


def test_paddleocr_block_must_resolve_to_single_field_label(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "blank_score_1": {
            "engine": "paddleocr",
            "fieldLabels": ["blankScore1..2"],
            "origin": [100, 100],
            "dimensions": [160, 60]
          }
        }
        """,
        '["blankScore1", "blankScore2"]',
    )

    with pytest.raises(Exception, match="must resolve to exactly one field label"):
        Template(template_path, CONFIG_DEFAULTS)
