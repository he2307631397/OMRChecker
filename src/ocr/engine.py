from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    raw: Any | None = None


class OcrEngine(Protocol):
    def recognize(self, image: Any, options: dict[str, Any] | None = None) -> OcrResult:
        ...


def normalize_paddleocr_result(raw: Any) -> OcrResult:
    lines: list[tuple[str, float]] = []
    for page in raw or []:
        for item in page or []:
            if not item or len(item) < 2:
                continue
            text_confidence = item[1]
            if not text_confidence or len(text_confidence) < 2:
                continue

            text, confidence = text_confidence[0], text_confidence[1]
            if text is None:
                continue
            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                confidence_value = 0.0
            lines.append((str(text), confidence_value))

    if not lines:
        return OcrResult(text="", confidence=0.0, raw=raw)

    text = "".join(line[0] for line in lines).strip()
    confidence = sum(line[1] for line in lines) / len(lines)
    return OcrResult(text=text, confidence=confidence, raw=raw)


class PaddleOcrEngine:
    def __init__(self) -> None:
        self._instances: dict[tuple[str, bool], Any] = {}

    def recognize(self, image: Any, options: dict[str, Any] | None = None) -> OcrResult:
        options = options or {}
        paddle = self._get_instance(options)
        raw = paddle.ocr(
            image,
            det=options.get("det", True),
            rec=options.get("rec", True),
            cls=options.get("cls", True),
        )
        return normalize_paddleocr_result(raw)

    def _get_instance(self, options: dict[str, Any]) -> Any:
        lang = options.get("lang", "ch")
        use_angle_cls = bool(options.get("cls", True))
        key = (lang, use_angle_cls)
        if key not in self._instances:
            try:
                paddleocr_module = importlib.import_module("paddleocr")
            except ImportError as exc:
                raise RuntimeError(
                    "PaddleOCR is required for fieldBlocks with engine='paddleocr'. "
                    "Install paddleocr and paddlepaddle CPU packages to enable OCR recognition."
                ) from exc

            self._instances[key] = paddleocr_module.PaddleOCR(
                lang=lang,
                use_angle_cls=use_angle_cls,
                use_gpu=False,
            )
        return self._instances[key]
