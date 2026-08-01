from dataclasses import dataclass

import numpy as np
from dotmap import DotMap

from src.core import ImageInstanceOps


@dataclass
class FakeBubble:
    field_label: str
    field_value: str
    x: int = 0
    y: int = 0


@dataclass
class FakeFieldBlock:
    field_type: str = "QTYPE_MCQ4"
    multi_select: bool = False
    bubble_dimensions: tuple[int, int] = (30, 18)
    shift: int = 0


def make_ops(**weak_overrides):
    params = {
        "enabled": True,
        "min_gap": 10,
        "min_delta_from_blank": 25,
        "adaptive_min_delta_from_blank": 12,
        "min_delta_from_page_blank": 20,
        "min_page_z_score": 2.0,
        "min_dark_pixel_ratio": 0.08,
        "min_density_gap": 0.03,
        "resolve_single_choice_conflicts": False,
        "conflict_min_gap": 5,
        "conflict_min_delta_from_blank": 12,
        "max_mean": 215,
        "supported_field_types": ["QTYPE_MCQ4"],
        "exclude_labels": [],
        "weak_fill_score_enabled": True,
        "weak_fill_min_score": 3.0,
        "weak_fill_review_min_score": 2.0,
        "weak_fill_min_page_delta": 12,
        "weak_fill_min_center_density": 0.12,
        "weak_fill_min_dark_ratio": 0.12,
        "weak_fill_max_ambiguity": 1.25,
    }
    params.update(weak_overrides)
    return ImageInstanceOps(DotMap({"outputs": {"save_image_level": 0}, "weak_mark_params": params}))


def make_bubbles():
    return [
        FakeBubble("q1", "A"),
        FakeBubble("q1", "B", x=35),
        FakeBubble("q1", "C", x=70),
        FakeBubble("q1", "D", x=105),
    ]


def make_image(fill_value=180, blank_value=240):
    image = np.full((30, 140), blank_value, dtype=np.uint8)
    image[5:13, 8:22] = fill_value
    return image


def test_feature_decision_accepts_general_page_supported_weak_mark():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = make_bubbles()
    diagnostics = ops.get_field_diagnostics([202.7, 208.6, 217.0, 219.0])
    diagnostics = ops.enrich_diagnostics_with_density(
        make_image(fill_value=180),
        field,
        bubbles,
        [202.7, 208.6, 217.0, 219.0],
        diagnostics,
        {"mean": 223.6, "std": 1.4},
    )

    decision = ops.get_single_choice_weak_fill_decision(diagnostics)

    assert decision["status"] == "WEAK_MARK"
    assert decision["score"] >= 3.0
    assert decision["reason"] == "feature_score"


def test_feature_decision_rejects_ambiguous_density_even_with_page_support():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = make_bubbles()
    diagnostics = ops.get_field_diagnostics([202.7, 203.1, 203.3, 203.4])
    diagnostics = ops.enrich_diagnostics_with_density(
        np.full((30, 140), 190, dtype=np.uint8),
        field,
        bubbles,
        [202.7, 203.1, 203.3, 203.4],
        diagnostics,
        {"mean": 223.6, "std": 1.4},
    )

    decision = ops.get_single_choice_weak_fill_decision(diagnostics)

    assert decision["status"] in {"REVIEW", "EMPTY"}
    assert decision["status"] != "WEAK_MARK"


def test_existing_disabled_config_keeps_fallback_off():
    ops = make_ops(enabled=False)
    assert not ops.tuning_config.weak_mark_params.enabled


def test_blank_single_choice_review_logging_does_not_auto_fill_when_score_supported(caplog):
    ops = make_ops(
        adaptive_min_delta_from_blank=40,
        weak_fill_score_enabled=True,
        weak_fill_min_score=3.0,
        weak_fill_review_min_score=2.0,
    )
    field = FakeFieldBlock()
    bubbles = make_bubbles()
    q_vals = [202.7, 208.6, 217.0, 219.0]

    result = ops.get_weak_marked_bubble(
        field,
        bubbles,
        q_vals,
        make_image(fill_value=180),
        {"mean": 223.6, "std": 1.4},
    )

    assert result is None
    assert "Weak mark candidate review" in caplog.text
    assert "status=WEAK_MARK" in caplog.text
    assert "score=" in caplog.text


def test_threshold_vote_features_count_stable_dynamic_threshold_support():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = make_bubbles()
    image = np.full((30, 140), 240, dtype=np.uint8)
    image[5:13, 8:22] = 180
    image[5:13, 43:57] = 235

    features = ops.get_threshold_vote_features(
        image,
        field,
        bubbles,
        blank_baseline=240,
        threshold_offsets=[10, 15, 20, 25],
    )

    assert features["threshold_vote_count"] == 4
    assert features["threshold_vote_total"] == 4
    assert features["threshold_vote_ratio"] == 1.0
    assert len(features["threshold_dark_ratios"]) == 4
    assert len(features["threshold_center_densities"]) == 4
    assert features["threshold_density_gaps"][0] > 0


def test_blank_single_choice_review_log_includes_threshold_votes(caplog):
    ops = make_ops(
        adaptive_min_delta_from_blank=40,
        weak_fill_score_enabled=True,
        weak_fill_min_score=3.0,
        weak_fill_review_min_score=2.0,
    )

    result = ops.get_weak_marked_bubble(
        FakeFieldBlock(),
        make_bubbles(),
        [202.7, 208.6, 217.0, 219.0],
        make_image(fill_value=180),
        {"mean": 223.6, "std": 1.4},
    )

    assert result is None
    assert "Weak mark candidate review" in caplog.text
    assert "threshold_vote_count=" in caplog.text
    assert "threshold_vote_ratio=" in caplog.text


def test_multiscale_roi_features_measure_scale_stability_for_center_mark():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = make_bubbles()
    image = np.full((30, 140), 240, dtype=np.uint8)
    image[5:13, 8:22] = 180

    features = ops.get_multiscale_roi_features(
        image,
        field,
        bubbles,
        blank_baseline=240,
    )

    assert features["multiscale_vote_count"] >= 2
    assert features["multiscale_vote_total"] >= 3
    assert features["multiscale_stability"] > 0.5
    assert len(features["multiscale_center_densities"]) == features["multiscale_vote_total"]
    assert len(features["multiscale_density_gaps"]) == features["multiscale_vote_total"]
    assert features["multiscale_density_gaps"][0] > 0


def test_blank_single_choice_review_log_includes_multiscale_features(caplog):
    ops = make_ops(
        adaptive_min_delta_from_blank=40,
        weak_fill_score_enabled=True,
        weak_fill_min_score=3.0,
        weak_fill_review_min_score=2.0,
    )

    result = ops.get_weak_marked_bubble(
        FakeFieldBlock(),
        make_bubbles(),
        [202.7, 208.6, 217.0, 219.0],
        make_image(fill_value=180),
        {"mean": 223.6, "std": 1.4},
    )

    assert result is None
    assert "Weak mark candidate review" in caplog.text
    assert "multiscale_vote_count=" in caplog.text
    assert "multiscale_stability=" in caplog.text


def test_blank_single_choice_review_records_candidate_confidence_metadata():
    ops = make_ops(
        adaptive_min_delta_from_blank=40,
        weak_fill_score_enabled=True,
        weak_fill_min_score=3.0,
        weak_fill_review_min_score=2.0,
    )

    result = ops.get_weak_marked_bubble(
        FakeFieldBlock(),
        make_bubbles(),
        [202.7, 208.6, 217.0, 219.0],
        make_image(fill_value=180),
        {"mean": 223.6, "std": 1.4},
    )

    assert result is None
    assert len(ops.last_weak_fill_reviews) == 1
    review = ops.last_weak_fill_reviews[0]
    assert review["field"] == "q1"
    assert review["candidate"] == "A"
    assert review["status"] == "WEAK_MARK"
    assert 0.0 <= review["confidence"] <= 1.0
    assert review["confidence"] > 0.5
    assert review["reason"] == "feature_score"
    assert "center_density" in review["evidence"]


def test_setup_outputs_adds_independent_weak_fill_review_csv_without_changing_results(
    tmp_path,
):
    from types import SimpleNamespace

    from src.utils.file import setup_outputs_for_template

    paths = SimpleNamespace(
        results_dir=tmp_path / "Results",
        manual_dir=tmp_path / "Manual",
    )
    paths.results_dir.mkdir()
    paths.manual_dir.mkdir()
    template = SimpleNamespace(output_columns=["q1", "q2"])

    outputs = setup_outputs_for_template(paths, template)

    results_header = (
        (tmp_path / "Results")
        .glob("Results_*.csv")
        .__next__()
        .read_text()
        .splitlines()[0]
    )
    review_header = (
        (tmp_path / "Results" / "WeakFillReview.csv")
        .read_text()
        .splitlines()[0]
    )

    assert results_header == '"file_id","input_path","output_path","score","q1","q2"'
    assert review_header.startswith(
        '"file_id","input_path","output_path","review_type","field",'
        '"original_value","candidate","confidence","status"'
    )
    assert "WeakFillReview" in outputs.files_obj


def test_review_csv_header_includes_review_type_and_original_value(tmp_path):
    from types import SimpleNamespace

    from src.utils.file import setup_outputs_for_template

    paths = SimpleNamespace(
        results_dir=tmp_path / "Results",
        manual_dir=tmp_path / "Manual",
    )
    paths.results_dir.mkdir()
    paths.manual_dir.mkdir()
    template = SimpleNamespace(output_columns=["q1", "q2"])

    setup_outputs_for_template(paths, template)

    header = (tmp_path / "Results" / "WeakFillReview.csv").read_text().splitlines()[0]
    assert header.startswith(
        '"file_id","input_path","output_path","review_type","field",'
        '"original_value","candidate","confidence","status"'
    )


def test_append_weak_fill_reviews_writes_one_row_per_candidate(tmp_path):
    from types import SimpleNamespace

    from src.entry import append_weak_fill_review_rows

    csv_path = tmp_path / "WeakFillReview.csv"
    review = {
        "field": "q5",
        "candidate": "D",
        "confidence": 0.73,
        "status": "WEAK_MARK",
        "reason": "feature_score",
        "evidence": "page_delta,density_gap",
        "score": 5.0,
        "legacy_rejection": "adaptive_min_delta_from_blank",
        "ambiguity": 0.1,
        "density_gap": 0.2,
        "center_density": 0.4,
        "center_edge_ratio": 4.0,
        "threshold_vote_ratio": 0.5,
        "multiscale_stability": 1.0,
    }
    outputs = SimpleNamespace(files_obj={"WeakFillReview": str(csv_path)})

    append_weak_fill_review_rows(
        "sheet.png",
        "/in/sheet.png",
        "/out/sheet.png",
        [review],
        outputs,
    )

    assert csv_path.read_text().splitlines() == [
        '"sheet.png","/in/sheet.png","/out/sheet.png","WEAK_MARK_REVIEW","q5","","D",'
        '"0.730","WEAK_MARK","feature_score","page_delta,density_gap","5.00",'
        '"adaptive_min_delta_from_blank","0.100","0.200","0.400",'
        '"4.000","0.500","1.000"'
    ]


def test_append_review_rows_writes_review_type_and_original_value(tmp_path):
    from types import SimpleNamespace

    from src.entry import append_weak_fill_review_rows

    csv_path = tmp_path / "WeakFillReview.csv"
    review = {
        "review_type": "SINGLE_CHOICE_CONFLICT_REVIEW",
        "field": "q1",
        "original_value": "ABCD",
        "candidate": "C",
        "confidence": 0.82,
        "status": "RESOLVED_CANDIDATE",
        "reason": "single_choice_conflict",
        "evidence": "gap,delta_from_blank,center_density",
        "score": 4.2,
        "legacy_rejection": "",
        "ambiguity": 0.08,
        "density_gap": 0.25,
        "center_density": 0.62,
        "center_edge_ratio": 6.0,
        "threshold_vote_ratio": 0.75,
        "multiscale_stability": 1.0,
    }
    outputs = SimpleNamespace(files_obj={"WeakFillReview": str(csv_path)})

    append_weak_fill_review_rows(
        "sheet.png",
        "/in/sheet.png",
        "/out/sheet.png",
        [review],
        outputs,
    )

    assert csv_path.read_text().splitlines() == [
        '"sheet.png","/in/sheet.png","/out/sheet.png",'
        '"SINGLE_CHOICE_CONFLICT_REVIEW","q1","ABCD","C","0.820",'
        '"RESOLVED_CANDIDATE","single_choice_conflict",'
        '"gap,delta_from_blank,center_density","4.20","",'
        '"0.080","0.250","0.620","6.000","0.750","1.000"'
    ]
