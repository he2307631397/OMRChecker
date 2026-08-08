import importlib
import sys

def test_interaction_import_uses_default_metrics_when_screeninfo_unavailable(monkeypatch):
    sys.modules.pop("src.utils.interaction", None)

    import screeninfo

    def raise_no_enumerators():
        raise screeninfo.common.ScreenInfoError("No enumerators available")

    monkeypatch.setattr(screeninfo, "get_monitors", raise_no_enumerators)

    interaction = importlib.import_module("src.utils.interaction")

    assert interaction.InteractionUtils.image_metrics.window_width == 1920
    assert interaction.InteractionUtils.image_metrics.window_height == 1080


def test_interaction_import_uses_detected_monitor_metrics(monkeypatch):
    sys.modules.pop("src.utils.interaction", None)

    import screeninfo

    class Monitor:
        width = 1366
        height = 768

    monkeypatch.setattr(screeninfo, "get_monitors", lambda: [Monitor()])

    interaction = importlib.import_module("src.utils.interaction")

    assert interaction.InteractionUtils.image_metrics.window_width == 1366
    assert interaction.InteractionUtils.image_metrics.window_height == 768
