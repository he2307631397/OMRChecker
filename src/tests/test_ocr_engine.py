import importlib
import sys
import types

import pytest

from src.ocr.engine import OcrResult, PaddleOcrEngine, normalize_paddleocr_result


def test_normalize_paddleocr_empty_result() -> None:
    assert normalize_paddleocr_result([]) == OcrResult(text="", confidence=0.0, raw=[])


def test_normalize_paddleocr_single_line_result() -> None:
    raw = [[[[[0, 0], [10, 0], [10, 10], [0, 10]], ("5", 0.98)]]]

    result = normalize_paddleocr_result(raw)

    assert result.text == "5"
    assert result.confidence == 0.98
    assert result.raw == raw


def test_normalize_paddleocr_multiple_lines_average_confidence() -> None:
    raw = [
        [
            [[[0, 0], [10, 0], [10, 10], [0, 10]], ("解", 0.9)],
            [[[0, 20], [10, 20], [10, 30], [0, 30]], ("答", 0.8)],
        ]
    ]

    result = normalize_paddleocr_result(raw)

    assert result.text == "解答"
    assert result.confidence == pytest.approx(0.85)


def test_paddleocr_engine_lazy_imports_dependency() -> None:
    engine = PaddleOcrEngine()

    assert "paddleocr" not in sys.modules
    assert engine._instances == {}


def test_paddleocr_engine_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "paddleocr":
            raise ImportError("missing paddleocr")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    engine = PaddleOcrEngine()
    with pytest.raises(RuntimeError, match="Install paddleocr and paddlepaddle CPU packages"):
        engine.recognize(image="fake-image")


def test_paddleocr_engine_uses_cpu_only_constructor_and_caches_by_lang_and_cls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed_options = []
    ocr_calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            constructed_options.append(kwargs)

        def ocr(self, image, **kwargs):
            ocr_calls.append((image, kwargs))
            return [[[[[0, 0], [1, 0], [1, 1], [0, 1]], ("7", 0.7)]]]

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)

    engine = PaddleOcrEngine()
    first = engine.recognize("image-1", {"lang": "en", "cls": False, "det": False})
    second = engine.recognize("image-2", {"lang": "en", "cls": False, "rec": False})

    assert first == OcrResult(
        text="7",
        confidence=0.7,
        raw=[[[[[0, 0], [1, 0], [1, 1], [0, 1]], ("7", 0.7)]]],
    )
    assert second.text == "7"
    assert constructed_options == [
        {
            "lang": "en",
            "use_angle_cls": False,
            "use_gpu": False,
        }
    ]
    assert ocr_calls == [
        ("image-1", {"det": False, "rec": True, "cls": False}),
        ("image-2", {"det": True, "rec": False, "cls": False}),
    ]
