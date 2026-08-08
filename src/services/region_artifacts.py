"""Local screenshot artifact generation for configured large answer-sheet regions."""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import cv2

from src.constants.common import FIELD_TYPES
from src.utils.parsing import parse_fields

from .batch_models import ArtifactPayload

_SAFE_FILENAME_PATTERN = re.compile(r"[^\w\u4e00-\u9fff.-]+", re.UNICODE)


class RegionLike(Protocol):
    region_code: str
    region_name: str
    type: str
    bbox: list[int]


@dataclass(frozen=True)
class RegionSpec:
    """Configured large business region in aligned sheet coordinates."""

    region_code: str
    region_name: str
    type: str
    bbox: list[int]


def load_template_archive_regions(template_dir: str | Path) -> list[RegionSpec]:
    """Load or derive archive screenshot regions for one template directory.

    Template-local ``regions.json`` is an optional explicit override. When it is
    absent, regions are derived from ``template.json`` field blocks so the same
    template definition drives both recognition and archive screenshots.
    """

    template_path = Path(template_dir) / "template.json"
    regions_path = Path(template_dir) / "regions.json"
    if regions_path.exists():
        return _load_regions_json(regions_path)
    if not template_path.exists():
        return []
    return derive_archive_regions_from_template(template_path)


def derive_archive_regions_from_template(template_path: str | Path, *, margin: int = 24) -> list[RegionSpec]:
    template = json.loads(Path(template_path).read_text(encoding="utf-8"))
    page_dimensions = template.get("pageDimensions") or [0, 0]
    page_width, page_height = _page_bounds(page_dimensions)
    default_bubble_dimensions = template.get("bubbleDimensions")
    grouped: dict[str, list[tuple[int, int, int, int]]] = {
        "candidateNumber": [],
        "singleChoice": [],
        "multiChoice": [],
    }
    ocr_specs: list[RegionSpec] = []

    for field_block in (template.get("fieldBlocks") or {}).values():
        if not isinstance(field_block, dict):
            continue
        if field_block.get("engine") == "paddleocr":
            ocr_spec = _ocr_region_spec_for_field_block(field_block)
            if ocr_spec is not None:
                ocr_specs.append(ocr_spec)
            continue
        region_code = _region_code_for_field_block(field_block)
        if region_code is None:
            continue
        bbox = _field_block_bbox(field_block, default_bubble_dimensions)
        if bbox is not None:
            grouped[region_code].append(bbox)

    specs = []
    labels = {
        "candidateNumber": ("准考证号区域", "DIGIT"),
        "singleChoice": ("单选题区域", "SINGLE_CHOICE"),
        "multiChoice": ("多选题区域", "MULTI_CHOICE"),
    }
    for region_code in ("candidateNumber", "singleChoice", "multiChoice"):
        boxes = grouped[region_code]
        if not boxes:
            continue
        region_name, region_type = labels[region_code]
        specs.append(
            RegionSpec(
                region_code=region_code,
                region_name=region_name,
                type=region_type,
                bbox=list(
                    _union_bbox(
                        boxes,
                        padding=_dynamic_region_padding(region_code, margin=margin, page_width=page_width, page_height=page_height),
                        page_width=page_width,
                        page_height=page_height,
                    )
                ),
            )
        )
    return [*specs, *ocr_specs]


def generate_region_artifacts(
    image_path: str | Path,
    regions: Sequence[RegionLike],
    output_dir: str | Path,
    *,
    sheet_id: str | None = None,
    task_id: str | None = None,
) -> list[ArtifactPayload]:
    """Crop configured large regions from an aligned sheet image into local artifacts.

    The caller supplies the large business regions to crop. This function never
    derives per-question or per-field crops from template details.
    """

    if not regions:
        return []

    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"unable to read image: {image_path}")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    artifacts: list[ArtifactPayload] = []
    for index, region in enumerate(regions, start=1):
        x, y, width, height = _validated_bbox(region, image.shape[1], image.shape[0])
        crop = image[y : y + height, x : x + width]
        filename = _artifact_filename(region, index=index, sheet_id=sheet_id)
        local_path = output_path / filename
        if not _write_image(local_path, crop):
            raise ValueError(f"unable to write region artifact: {local_path}")

        metadata: dict[str, object] = {
            "localPath": str(local_path),
            "regionCode": region.region_code,
            "regionName": region.region_name,
            "regionType": region.type,
            "bbox": {"x": x, "y": y, "width": width, "height": height},
        }
        if sheet_id is not None:
            metadata["sheetId"] = sheet_id
        if task_id is not None:
            metadata["taskId"] = task_id

        artifacts.append(
            ArtifactPayload(
                artifact_type="region_screenshot",
                osskey=str(local_path),
                metadata=metadata,
            )
        )

    return artifacts


def _load_regions_json(regions_path: Path) -> list[RegionSpec]:
    raw_regions = json.loads(regions_path.read_text(encoding="utf-8"))
    if isinstance(raw_regions, dict):
        raw_regions = raw_regions.get("archiveRegions", [])
    if not isinstance(raw_regions, list):
        raise ValueError(f"regions.json must contain a list or archiveRegions object: {regions_path}")
    return [
        RegionSpec(
            region_code=str(region.get("regionCode", "")),
            region_name=str(region.get("regionName", "")),
            type=str(region.get("type", "")),
            bbox=[int(value) for value in region.get("bbox", [])],
        )
        for region in raw_regions
        if isinstance(region, dict)
    ]


def _page_bounds(page_dimensions) -> tuple[int, int]:
    if isinstance(page_dimensions, list) and len(page_dimensions) == 2:
        try:
            return int(page_dimensions[0]), int(page_dimensions[1])
        except (TypeError, ValueError):
            return 0, 0
    return 0, 0


def _region_code_for_field_block(field_block: dict) -> str | None:
    field_type = field_block.get("fieldType")
    if field_type in {"QTYPE_INT", "QTYPE_INT_FROM_1"}:
        return "candidateNumber"
    if isinstance(field_type, str) and field_type.startswith("QTYPE_MCQ"):
        return "multiChoice" if field_block.get("multiSelect") is True else "singleChoice"
    return None


def _field_block_bbox(field_block: dict, default_bubble_dimensions) -> tuple[int, int, int, int] | None:
    field_type = field_block.get("fieldType")
    merged = {**FIELD_TYPES.get(field_type, {}), **field_block}
    origin = merged.get("origin")
    bubble_dimensions = merged.get("bubbleDimensions") or default_bubble_dimensions
    bubble_values = merged.get("bubbleValues")
    field_labels = merged.get("fieldLabels")
    if not _two_numbers(origin) or not _two_numbers(bubble_dimensions) or not isinstance(bubble_values, list):
        return None
    try:
        parsed_labels = parse_fields("Archive Region Field Block", field_labels or [])
    except Exception:
        return None
    if not parsed_labels or not bubble_values:
        return None

    x, y = int(origin[0]), int(origin[1])
    bubble_width, bubble_height = int(bubble_dimensions[0]), int(bubble_dimensions[1])
    bubbles_gap = int(merged.get("bubblesGap", 0))
    labels_gap = int(merged.get("labelsGap", 0))
    direction = merged.get("direction", "vertical")
    if direction == "vertical":
        width = labels_gap * (len(parsed_labels) - 1) + bubble_width
        height = bubbles_gap * (len(bubble_values) - 1) + bubble_height
    else:
        width = bubbles_gap * (len(bubble_values) - 1) + bubble_width
        height = labels_gap * (len(parsed_labels) - 1) + bubble_height
    return x, y, width, height


def _ocr_region_spec_for_field_block(field_block: dict) -> RegionSpec | None:
    ocr_options = field_block.get("ocr") or {}
    if isinstance(ocr_options, dict) and ocr_options.get("archiveRegion") is False:
        return None

    origin = field_block.get("origin")
    dimensions = field_block.get("dimensions")
    if not _two_numbers(origin) or not _two_numbers(dimensions):
        return None

    region_code = field_block.get("regionCode")
    region_name = field_block.get("regionName") or field_block.get("name")
    region_type = field_block.get("type")
    if not region_code or not region_name or not region_type:
        return None

    x, y = int(origin[0]), int(origin[1])
    width, height = int(dimensions[0]), int(dimensions[1])
    if width <= 0 or height <= 0:
        return None

    return RegionSpec(
        region_code=str(region_code),
        region_name=str(region_name),
        type=str(region_type),
        bbox=[x, y, width, height],
    )


def _two_numbers(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, int | float) for item in value)


def _union_bbox(
    boxes: Sequence[tuple[int, int, int, int]],
    *,
    padding: tuple[int, int, int, int],
    page_width: int,
    page_height: int,
) -> tuple[int, int, int, int]:
    pad_left, pad_top, pad_right, pad_bottom = padding
    left = min(x for x, _y, _width, _height in boxes) - pad_left
    top = min(y for _x, y, _width, _height in boxes) - pad_top
    right = max(x + width for x, _y, width, _height in boxes) + pad_right
    bottom = max(y + height for _x, y, _width, height in boxes) + pad_bottom
    left = max(0, left)
    top = max(0, top)
    if page_width > 0:
        right = min(page_width, right)
    if page_height > 0:
        bottom = min(page_height, bottom)
    return left, top, max(1, right - left), max(1, bottom - top)


def _dynamic_region_padding(region_code: str, *, margin: int, page_width: int, page_height: int) -> tuple[int, int, int, int]:
    """Return left/top/right/bottom expansion for template-derived region crops.

    Template field block origins describe bubble grids. Archive screenshots need
    a larger business area: question number/title text usually sits left/above
    the bubbles, and admission-number templates commonly have handwritten name
    or number areas to the left/above the fill bubbles.
    """

    if region_code == "candidateNumber":
        return (
            max(margin, _ratio_pixels(page_width, 0.45), 220),
            max(margin, _ratio_pixels(page_height, 0.08), 90),
            margin,
            margin,
        )
    if region_code in {"singleChoice", "multiChoice"}:
        return (
            max(margin, _ratio_pixels(page_width, 0.08), 80),
            max(margin, _ratio_pixels(page_height, 0.04), 48),
            margin,
            margin,
        )
    return margin, margin, margin, margin


def _ratio_pixels(total: int, ratio: float) -> int:
    return int(round(total * ratio)) if total > 0 else 0


def _validated_bbox(region: RegionLike, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    if len(region.bbox) != 4:
        raise ValueError(f"region bbox must contain x, y, width, height for {region.region_code}")

    x, y, width, height = region.bbox
    if any(not isinstance(value, int) for value in (x, y, width, height)):
        raise ValueError(f"region bbox values must be integers for {region.region_code}")
    if width <= 0 or height <= 0:
        raise ValueError(f"region bbox width and height must be positive for {region.region_code}")
    if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
        raise ValueError(
            f"region bbox is outside image bounds for {region.region_code}: "
            f"bbox={[x, y, width, height]}, image={{'width': {image_width}, 'height': {image_height}}}"
        )
    return x, y, width, height


def _artifact_filename(region: RegionLike, *, index: int, sheet_id: str | None) -> str:
    parts = [part for part in (sheet_id, region.region_code, region.region_name) if part]
    stem = "_".join(_sanitize_filename_part(part) for part in parts)
    if not stem:
        stem = "region"
    return f"{index:03d}_{stem}.png"


def _sanitize_filename_part(value: str) -> str:
    sanitized = _SAFE_FILENAME_PATTERN.sub("_", value.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "region"


def _write_image(path: Path, image) -> bool:
    """Write an image while supporting Unicode paths on Windows.

    OpenCV's ``imwrite`` can fail for non-ASCII paths on some Windows builds.
    Encoding first and writing bytes through Python keeps the existing filenames
    while using Windows' Unicode-aware filesystem APIs.
    """

    success, encoded = cv2.imencode(path.suffix or ".png", image)
    if not success:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            handle.write(encoded.tobytes())
    except OSError:
        return False
    return True
