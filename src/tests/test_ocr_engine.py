import importlib
import sys
import types

import numpy as np
import pytest

from src.ocr.engine import OcrResult, PaddleOcrEngine, normalize_paddleocr_result


@pytest.fixture(autouse=True)
def clear_thread_local_ocr_instances():
    PaddleOcrEngine._thread_local.instances = {}
    yield
    PaddleOcrEngine._thread_local.instances = {}


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


def test_normalize_paddleocr_v3_dict_result() -> None:
    raw = [{"rec_texts": ["解", "答"], "rec_scores": [0.9, 0.8]}]

    result = normalize_paddleocr_result(raw)

    assert result.text == "解答"
    assert result.confidence == pytest.approx(0.85)
    assert result.raw == raw


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

        def ocr(self, image):
            ocr_calls.append(image)
            return [{"rec_texts": ["7"], "rec_scores": [0.7]}]

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)

    engine = PaddleOcrEngine()
    first = engine.recognize("image-1", {"lang": "en", "cls": False, "det": False})
    second = engine.recognize("image-2", {"lang": "en", "cls": False, "rec": False})

    assert first == OcrResult(
        text="7",
        confidence=0.7,
        raw=[{"rec_texts": ["7"], "rec_scores": [0.7]}],
    )
    assert second.text == "7"
    assert constructed_options == [
        {
            "lang": "en",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
    ]
    assert ocr_calls == ["image-1", "image-2"]


def test_paddleocr_engine_reuses_thread_local_instances_across_engine_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed_options = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            constructed_options.append(kwargs)

        def ocr(self, image):
            return [{"rec_texts": [str(image)], "rec_scores": [0.9]}]

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)

    first = PaddleOcrEngine().recognize("1", {"lang": "en"})
    second = PaddleOcrEngine().recognize("2", {"lang": "en"})

    assert first.text == "1"
    assert second.text == "2"
    assert len(constructed_options) == 1


def test_paddleocr_engine_passes_runtime_detection_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr_call_options = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            pass

        def ocr(self, image, **kwargs):
            ocr_call_options.append(kwargs)
            return [{"rec_texts": ["9"], "rec_scores": [0.9]}]

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module)

    result = PaddleOcrEngine().recognize("image", {"det": False, "rec": True, "cls": False})

    assert result.text == "9"
    assert ocr_call_options == [{"det": False, "rec": True, "cls": False}]


def test_paddleocr_engine_converts_grayscale_crops_to_three_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr_calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            pass

        def ocr(self, image):
            ocr_calls.append(image)
            return [{"rec_texts": ["8"], "rec_scores": [0.8]}]

    fake_module = types.SimpleNamespace(PaddleOCR=FakePaddleOCR)
    real_import_module = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: fake_module if name == "paddleocr" else real_import_module(name),
    )

    grayscale = np.zeros((10, 12), dtype=np.uint8)

    result = PaddleOcrEngine().recognize(grayscale)

    assert result.text == "8"
    assert ocr_calls[0].shape == (10, 12, 3)
