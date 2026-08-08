from __future__ import annotations

from typing import Any


def crop_ocr_region(image: Any, field_block: Any):
    x, y = field_block.origin
    width, height = field_block.dimensions
    image_height, image_width = image.shape[:2]
    bbox = [x, y, width, height]

    if (
        x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > image_width
        or y + height > image_height
    ):
        raise ValueError(
            f"OCR field block '{field_block.name}' bbox {bbox} is outside image bounds "
            f"{[image_width, image_height]}"
        )

    return image[y : y + height, x : x + width].copy()
