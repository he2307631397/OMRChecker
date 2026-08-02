"""Local screenshot artifact generation for configured large answer-sheet regions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import cv2

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
        if not cv2.imwrite(str(local_path), crop):
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
