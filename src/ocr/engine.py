from __future__ import annotations

import importlib
import threading
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
        if isinstance(page, dict):
            texts = page.get("rec_texts") or []
            scores = page.get("rec_scores") or []
            for text, confidence in zip(texts, scores, strict=False):
                if text is None:
                    continue
                try:
                    confidence_value = float(confidence)
                except (TypeError, ValueError):
                    confidence_value = 0.0
                lines.append((str(text), confidence_value))
            continue

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
    _thread_local = threading.local()

    def __init__(self) -> None:
        self._instances = self._thread_instances()

    def recognize(self, image: Any, options: dict[str, Any] | None = None) -> OcrResult:
        options = options or {}
        paddle = self._get_instance(options)
        raw = self._call_paddle_ocr(paddle, self._ensure_three_channel_image(image), options)
        return normalize_paddleocr_result(raw)

    @classmethod
    def _thread_instances(cls) -> dict[tuple[str, bool], Any]:
        instances = getattr(cls._thread_local, "instances", None)
        if instances is None:
            instances = {}
            cls._thread_local.instances = instances
        return instances

    @staticmethod
    def _call_paddle_ocr(paddle: Any, image: Any, options: dict[str, Any]) -> Any:
        call_options = {
            key: bool(options[key])
            for key in ("det", "rec", "cls")
            if key in options
        }
        if not call_options:
            return paddle.ocr(image)
        try:
            return paddle.ocr(image, **call_options)
        except TypeError as exc:
            if "unexpected" not in str(exc) and "keyword" not in str(exc):
                raise
            return paddle.ocr(image)

    @staticmethod
    def _ensure_three_channel_image(image: Any) -> Any:
        shape = getattr(image, "shape", None)
        if shape is None or len(shape) != 2:
            return image

        try:
            cv2_module = importlib.import_module("cv2")
        except ImportError:
            return image
        return cv2_module.cvtColor(image, cv2_module.COLOR_GRAY2BGR)

    def _get_instance(self, options: dict[str, Any]) -> Any:
        lang = options.get("lang", "ch")
        use_textline_orientation = bool(options.get("cls", False))
        key = (lang, use_textline_orientation)
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
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=use_textline_orientation,
            )
        return self._instances[key]
