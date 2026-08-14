import os
from collections import defaultdict
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np

from src.constants.common import (
    CLR_BLACK,
    CLR_DARK_GRAY,
    CLR_GRAY,
    GLOBAL_PAGE_THRESHOLD_BLACK,
    GLOBAL_PAGE_THRESHOLD_WHITE,
    TEXT_SIZE,
)
from src.logger import logger
from src.ocr.engine import PaddleOcrEngine
from src.ocr.region import crop_ocr_region
from src.utils.image import CLAHE_HELPER, ImageUtils
from src.utils.interaction import InteractionUtils


class ImageInstanceOps:
    """Class to hold fine-tuned utilities for a group of images. One instance for each processing directory."""

    save_img_list: Any = defaultdict(list)

    def __init__(self, tuning_config, ocr_engine=None):
        super().__init__()
        self.tuning_config = tuning_config
        self.save_image_level = tuning_config.outputs.save_image_level
        self.last_weak_fill_reviews = []
        self.last_ocr_results = {}
        self.ocr_engine = ocr_engine or PaddleOcrEngine()

    def apply_preprocessors(self, file_path, in_omr, template):
        tuning_config = self.tuning_config
        # resize to conform to template
        in_omr = ImageUtils.resize_util(
            in_omr,
            tuning_config.dimensions.processing_width,
            tuning_config.dimensions.processing_height,
        )

        # run pre_processors in sequence
        for pre_processor in template.pre_processors:
            in_omr = pre_processor.apply_filter(in_omr, file_path)
            if in_omr is None:
                break
        return in_omr

    def read_ocr_response(self, image, field_block):
        field_label = field_block.parsed_field_labels[0]
        crop = crop_ocr_region(image, field_block)
        result = self.ocr_engine.recognize(crop, field_block.ocr_options)
        text = self.normalize_ocr_text(result.text, field_block)
        x, y = field_block.origin
        width, height = field_block.dimensions
        self.last_ocr_results[field_label] = {
            "text": text,
            "confidence": result.confidence,
            "engine": "paddleocr",
            "blockName": field_block.name,
            "bbox": [x, y, width, height],
            "regionCode": field_block.region_code,
            "regionName": field_block.region_name,
            "type": field_block.region_type,
        }
        return field_label, text

    @staticmethod
    def normalize_ocr_text(text, field_block):
        options = field_block.ocr_options or {}
        if options.get("digitsOnly") is not True:
            return text
        normalized = str(text or "")
        replacements = {
            "O": "0",
            "o": "0",
            "〇": "0",
            "○": "0",
            "一": "1",
            "I": "1",
            "l": "1",
            "|": "1",
            "/": "1",
            "／": "1",
            "S": "5",
            "s": "5",
        }
        normalized = "".join(replacements.get(ch, ch) for ch in normalized)
        return "".join(ch for ch in normalized if ch.isdigit())

    @staticmethod
    def get_page_blank_model(q_vals):
        """Estimate page-level blank bubble appearance using robust light samples."""
        if not q_vals:
            return {"mean": 255.0, "std": 1.0, "count": 0}

        sorted_vals = sorted(float(v) for v in q_vals)
        blank_start = int(len(sorted_vals) * 0.75)
        blank_vals = sorted_vals[blank_start:] or sorted_vals
        blank_mean = float(np.mean(blank_vals))
        blank_std = float(np.std(blank_vals))
        # Keep z-score usable on very uniform pages.
        return {"mean": blank_mean, "std": max(blank_std, 1.0), "count": len(blank_vals)}

    @staticmethod
    def get_field_diagnostics(q_strip_vals):
        """Return local relative statistics for candidates in one field."""
        sorted_candidates = sorted(
            enumerate(float(v) for v in q_strip_vals), key=lambda item: item[1]
        )
        darkest_index, darkest_mean = sorted_candidates[0]
        second_darkest_mean = sorted_candidates[1][1] if len(sorted_candidates) > 1 else 255.0
        sorted_vals = sorted(float(v) for v in q_strip_vals)
        lighter_half = sorted_vals[len(sorted_vals) // 2 :] or sorted_vals
        blank_baseline = float(np.mean(lighter_half))
        blank_std = max(float(np.std(lighter_half)), 1.0)
        delta_from_blank = blank_baseline - darkest_mean
        gap = second_darkest_mean - darkest_mean
        return {
            "darkest_index": darkest_index,
            "darkest_mean": darkest_mean,
            "second_darkest_mean": second_darkest_mean,
            "gap": gap,
            "blank_baseline": blank_baseline,
            "blank_std": blank_std,
            "delta_from_blank": delta_from_blank,
            "local_z_score": delta_from_blank / blank_std,
        }

    @staticmethod
    def get_candidate_density(image, field_block, bubble, blank_baseline):
        """Measure dark-pixel density in an inner bubble ROI.

        The inner ROI reduces printed border influence. The threshold is relative
        to the field/page blank baseline so the feature follows scan brightness.
        """
        box_w, box_h = field_block.bubble_dimensions
        x, y = (bubble.x + field_block.shift, bubble.y)
        pad_x = max(1, int(box_w / 6))
        pad_y = max(1, int(box_h / 6))
        roi = image[y + pad_y : y + box_h - pad_y, x + pad_x : x + box_w - pad_x]
        if roi.size == 0:
            return 0.0
        threshold = max(0, blank_baseline - 20)
        return float(np.mean(roi < threshold))

    @staticmethod
    def get_candidate_density_features(image, field_block, bubble, blank_baseline):
        """Return general dark-pixel density features for one bubble ROI."""
        box_w, box_h = field_block.bubble_dimensions
        x, y = (bubble.x + field_block.shift, bubble.y)
        roi = image[y : y + box_h, x : x + box_w]
        if roi.size == 0:
            return {
                "dark_ratio": 0.0,
                "center_density": 0.0,
                "edge_density": 0.0,
                "center_edge_ratio": 0.0,
            }

        threshold = max(0, blank_baseline - 20)
        dark_mask = roi < threshold
        dark_ratio = float(np.mean(dark_mask))

        pad_x = max(1, int(box_w / 4))
        pad_y = max(1, int(box_h / 4))
        center = dark_mask[pad_y : box_h - pad_y, pad_x : box_w - pad_x]
        center_density = float(np.mean(center)) if center.size else 0.0

        edge_mask = dark_mask.copy()
        if center.size:
            edge_mask[pad_y : box_h - pad_y, pad_x : box_w - pad_x] = False
        edge_count = edge_mask.size - center.size
        edge_density = float(np.sum(edge_mask) / max(edge_count, 1))
        center_edge_ratio = center_density / max(edge_density, 0.01)

        return {
            "dark_ratio": dark_ratio,
            "center_density": center_density,
            "edge_density": edge_density,
            "center_edge_ratio": center_edge_ratio,
        }

    @staticmethod
    def get_threshold_vote_features(
        image, field_block, field_block_bubbles, blank_baseline, threshold_offsets=None
    ):
        """Return dynamic-threshold vote features for a single-choice field.

        Each offset creates a threshold relative to the local blank baseline. The
        darkest candidate receives one vote when its center density is strictly
        higher than the next candidate at that threshold. This is observation
        evidence only and does not change the legacy answer selection.
        """
        if threshold_offsets is None:
            threshold_offsets = [10, 15, 20, 25]

        vote_count = 0
        darkest_indices = []
        darkest_dark_ratios = []
        darkest_center_densities = []
        density_gaps = []
        box_w, box_h = field_block.bubble_dimensions

        for offset in threshold_offsets:
            threshold = max(0, float(blank_baseline) - float(offset))
            candidate_features = []
            for bubble in field_block_bubbles:
                x, y = (bubble.x + field_block.shift, bubble.y)
                roi = image[y : y + box_h, x : x + box_w]
                if roi.size == 0:
                    candidate_features.append((0.0, 0.0))
                    continue

                dark_mask = roi < threshold
                dark_ratio = float(np.mean(dark_mask))
                pad_x = max(1, int(box_w / 4))
                pad_y = max(1, int(box_h / 4))
                center = dark_mask[pad_y : box_h - pad_y, pad_x : box_w - pad_x]
                center_density = float(np.mean(center)) if center.size else 0.0
                candidate_features.append((dark_ratio, center_density))

            ranked = sorted(
                enumerate(candidate_features),
                key=lambda item: (item[1][1], item[1][0]),
                reverse=True,
            )
            if not ranked:
                darkest_indices.append(-1)
                darkest_dark_ratios.append(0.0)
                darkest_center_densities.append(0.0)
                density_gaps.append(0.0)
                continue

            darkest_index, (dark_ratio, center_density) = ranked[0]
            second_density = ranked[1][1][1] if len(ranked) > 1 else 0.0
            density_gap = center_density - second_density
            if center_density > 0 and density_gap > 0:
                vote_count += 1
            darkest_indices.append(darkest_index)
            darkest_dark_ratios.append(dark_ratio)
            darkest_center_densities.append(center_density)
            density_gaps.append(density_gap)

        total = len(threshold_offsets)
        return {
            "threshold_vote_count": vote_count,
            "threshold_vote_total": total,
            "threshold_vote_ratio": vote_count / max(total, 1),
            "threshold_vote_indices": darkest_indices,
            "threshold_dark_ratios": darkest_dark_ratios,
            "threshold_center_densities": darkest_center_densities,
            "threshold_density_gaps": density_gaps,
        }

    @staticmethod
    def get_multiscale_roi_features(image, field_block, field_block_bubbles, blank_baseline):
        """Return small image-pyramid ROI stability features for a field.

        The variants intentionally stay local to the bubble ROI: original ROI,
        center-cropped ROI, lightly blurred ROI, and a down/up-sampled ROI. These
        features are used for observation only and never override main detection.
        """
        box_w, box_h = field_block.bubble_dimensions
        threshold = max(0, float(blank_baseline) - 20)
        variants = ("original", "center", "blur", "pyramid")
        vote_count = 0
        vote_indices = []
        center_densities = []
        density_gaps = []

        for variant in variants:
            candidate_densities = []
            for bubble in field_block_bubbles:
                x, y = (bubble.x + field_block.shift, bubble.y)
                roi = image[y : y + box_h, x : x + box_w]
                if roi.size == 0:
                    candidate_densities.append(0.0)
                    continue

                if variant == "center":
                    pad_x = max(1, int(box_w / 4))
                    pad_y = max(1, int(box_h / 4))
                    roi = roi[pad_y : box_h - pad_y, pad_x : box_w - pad_x]
                elif variant == "blur":
                    roi = cv2.GaussianBlur(roi, (3, 3), 0)
                elif variant == "pyramid":
                    down_w = max(1, int(roi.shape[1] * 0.75))
                    down_h = max(1, int(roi.shape[0] * 0.75))
                    roi = cv2.resize(roi, (down_w, down_h), interpolation=cv2.INTER_AREA)
                    roi = cv2.resize(roi, (box_w, box_h), interpolation=cv2.INTER_LINEAR)

                candidate_densities.append(float(np.mean(roi < threshold)))

            ranked = sorted(enumerate(candidate_densities), key=lambda item: item[1], reverse=True)
            if not ranked:
                vote_indices.append(-1)
                center_densities.append(0.0)
                density_gaps.append(0.0)
                continue

            darkest_index, darkest_density = ranked[0]
            second_density = ranked[1][1] if len(ranked) > 1 else 0.0
            density_gap = darkest_density - second_density
            if darkest_density > 0 and density_gap > 0:
                vote_count += 1
            vote_indices.append(darkest_index)
            center_densities.append(darkest_density)
            density_gaps.append(density_gap)

        total = len(variants)
        return {
            "multiscale_vote_count": vote_count,
            "multiscale_vote_total": total,
            "multiscale_stability": vote_count / max(total, 1),
            "multiscale_vote_indices": vote_indices,
            "multiscale_center_densities": center_densities,
            "multiscale_density_gaps": density_gaps,
        }

    def enrich_diagnostics_with_density(
        self, image, field_block, field_block_bubbles, q_strip_vals, diagnostics, page_blank_model
    ):
        densities = []
        density_features = []
        for bubble in field_block_bubbles:
            densities.append(
                self.get_candidate_density(
                    image, field_block, bubble, diagnostics["blank_baseline"]
                )
            )
            density_features.append(
                self.get_candidate_density_features(
                    image, field_block, bubble, diagnostics["blank_baseline"]
                )
            )
        darkest_index = diagnostics["darkest_index"]
        sorted_densities = sorted(densities, reverse=True)
        darkest_density = densities[darkest_index] if densities else 0.0
        second_density = sorted_densities[1] if len(sorted_densities) > 1 else 0.0
        diagnostics.update(
            {
                "densities": densities,
                "darkest_density": darkest_density,
                "second_density": second_density,
                "density_gap": darkest_density - second_density,
                "dark_ratios": [item["dark_ratio"] for item in density_features],
                "center_densities": [
                    item["center_density"] for item in density_features
                ],
                "edge_densities": [item["edge_density"] for item in density_features],
                "center_edge_ratios": [
                    item["center_edge_ratio"] for item in density_features
                ],
                "darkest_dark_ratio": density_features[darkest_index]["dark_ratio"]
                if density_features
                else 0.0,
                "darkest_center_density": density_features[darkest_index][
                    "center_density"
                ]
                if density_features
                else 0.0,
                "darkest_edge_density": density_features[darkest_index][
                    "edge_density"
                ]
                if density_features
                else 0.0,
                "darkest_center_edge_ratio": density_features[darkest_index][
                    "center_edge_ratio"
                ]
                if density_features
                else 0.0,
                "page_blank_mean": page_blank_model["mean"],
                "page_blank_std": page_blank_model["std"],
                "delta_from_page_blank": page_blank_model["mean"]
                - diagnostics["darkest_mean"],
                "page_z_score": (page_blank_model["mean"] - diagnostics["darkest_mean"])
                / page_blank_model["std"],
            }
        )
        diagnostics.update(
            self.get_threshold_vote_features(
                image,
                field_block,
                field_block_bubbles,
                diagnostics["blank_baseline"],
                getattr(
                    self.tuning_config.weak_mark_params,
                    "threshold_vote_offsets",
                    None,
                ),
            )
        )
        diagnostics.update(
            self.get_multiscale_roi_features(
                image,
                field_block,
                field_block_bubbles,
                diagnostics["blank_baseline"],
            )
        )
        return diagnostics

    def get_single_choice_weak_fill_decision(self, diagnostics):
        """Classify a blank single-choice weak-fill candidate from reusable features."""
        weak_mark_params = self.tuning_config.weak_mark_params
        if not getattr(weak_mark_params, "weak_fill_score_enabled", False):
            return {"status": "LEGACY", "score": 0.0, "reason": "score_disabled"}

        page_delta = diagnostics["delta_from_page_blank"]
        page_z = diagnostics["page_z_score"]
        local_delta = diagnostics["delta_from_blank"]
        gap = diagnostics["gap"]
        dark_ratio = diagnostics.get(
            "darkest_dark_ratio", diagnostics.get("darkest_density", 0.0)
        )
        center_density = diagnostics.get(
            "darkest_center_density", diagnostics.get("darkest_density", 0.0)
        )
        center_edge_ratio = diagnostics.get("darkest_center_edge_ratio", 0.0)
        density_gap = diagnostics.get("density_gap", 0.0)

        score = 0.0
        reasons = []
        if page_delta >= weak_mark_params.weak_fill_min_page_delta:
            score += 1.0
            reasons.append("page_delta")
        if page_z >= weak_mark_params.min_page_z_score:
            score += 1.0
            reasons.append("page_z")
        if dark_ratio >= weak_mark_params.weak_fill_min_dark_ratio:
            score += 1.0
            reasons.append("dark_ratio")
        if center_density >= weak_mark_params.weak_fill_min_center_density:
            score += 1.0
            reasons.append("center_density")
        if center_edge_ratio >= 1.0:
            score += 0.5
            reasons.append("center_edge")
        if local_delta >= weak_mark_params.adaptive_min_delta_from_blank:
            score += 0.75
            reasons.append("local_delta")
        if gap >= weak_mark_params.min_gap:
            score += 0.75
            reasons.append("gap")
        if density_gap >= weak_mark_params.min_density_gap:
            score += 0.5
            reasons.append("density_gap")

        ambiguity = 0.0
        if gap < weak_mark_params.min_gap:
            ambiguity += (weak_mark_params.min_gap - gap) / max(
                weak_mark_params.min_gap, 1
            )
        if density_gap < 0:
            ambiguity += abs(density_gap) * 2

        if ambiguity > weak_mark_params.weak_fill_max_ambiguity:
            return {
                "status": "REVIEW",
                "score": score,
                "reason": "ambiguous",
                "evidence": reasons,
                "ambiguity": ambiguity,
            }
        if score >= weak_mark_params.weak_fill_min_score:
            return {
                "status": "WEAK_MARK",
                "score": score,
                "reason": "feature_score",
                "evidence": reasons,
                "ambiguity": ambiguity,
            }
        if score >= weak_mark_params.weak_fill_review_min_score:
            return {
                "status": "REVIEW",
                "score": score,
                "reason": "low_score",
                "evidence": reasons,
                "ambiguity": ambiguity,
            }
        return {
            "status": "EMPTY",
            "score": score,
            "reason": "low_score",
            "evidence": reasons,
            "ambiguity": ambiguity,
        }

    @staticmethod
    def get_weak_fill_confidence(score_decision, diagnostics):
        """Convert weak-fill evidence into a bounded review confidence."""
        score_component = min(float(score_decision.get("score", 0.0)) / 6.0, 1.0)
        density_component = min(max(diagnostics.get("density_gap", 0.0), 0.0) / 0.25, 1.0)
        center_component = min(diagnostics.get("darkest_center_density", 0.0) / 0.6, 1.0)
        threshold_component = diagnostics.get("threshold_vote_ratio", 0.0)
        multiscale_component = diagnostics.get("multiscale_stability", 0.0)
        confidence = (
            score_component * 0.30
            + density_component * 0.25
            + center_component * 0.20
            + threshold_component * 0.10
            + multiscale_component * 0.15
        )
        return max(0.0, min(confidence, 1.0))

    @staticmethod
    def get_single_choice_conflict_confidence(diagnostics):
        """Convert single-choice conflict separation into a bounded confidence."""
        gap_component = min(max(diagnostics.get("gap", 0.0), 0.0) / 20.0, 1.0)
        delta_component = min(
            max(diagnostics.get("delta_from_blank", 0.0), 0.0) / 40.0, 1.0
        )
        confidence = gap_component * 0.55 + delta_component * 0.45
        return max(0.0, min(confidence, 1.0))

    @staticmethod
    def get_identifier_review_confidence(diagnostics):
        """Convert weak identifier evidence into a bounded review confidence."""
        gap_component = min(max(diagnostics.get("gap", 0.0), 0.0) / 25.0, 1.0)
        delta_component = min(
            max(diagnostics.get("delta_from_blank", 0.0), 0.0) / 45.0, 1.0
        )
        page_component = min(max(diagnostics.get("page_z_score", 0.0), 0.0) / 10.0, 1.0)
        density_component = min(
            max(diagnostics.get("density_gap", 0.0), 0.0) / 0.25, 1.0
        )
        confidence = (
            gap_component * 0.30
            + delta_component * 0.30
            + page_component * 0.20
            + density_component * 0.20
        )
        return max(0.0, min(confidence, 1.0))

    def append_weak_fill_review(
        self, field_label, candidate, score_decision, diagnostics, legacy_rejection
    ):
        """Store one review candidate for auxiliary CSV/report outputs."""
        confidence = self.get_weak_fill_confidence(score_decision, diagnostics)
        self.last_weak_fill_reviews.append(
            {
                "field": field_label,
                "candidate": candidate,
                "status": score_decision["status"],
                "confidence": confidence,
                "score": score_decision.get("score", 0.0),
                "reason": score_decision.get("reason", ""),
                "legacy_rejection": legacy_rejection,
                "evidence": ",".join(score_decision.get("evidence", [])),
                "ambiguity": score_decision.get("ambiguity", 0.0),
                "density_gap": diagnostics.get("density_gap", 0.0),
                "center_density": diagnostics.get("darkest_center_density", 0.0),
                "center_edge_ratio": diagnostics.get("darkest_center_edge_ratio", 0.0),
                "threshold_vote_ratio": diagnostics.get("threshold_vote_ratio", 0.0),
                "multiscale_stability": diagnostics.get("multiscale_stability", 0.0),
            }
        )

    def get_weak_fill_review_restore_status(self, score_decision, diagnostics):
        """Return confidence-based restore status for a reviewed weak-fill candidate."""
        confidence = self.get_weak_fill_confidence(score_decision, diagnostics)
        weak_mark_params = self.tuning_config.weak_mark_params
        auto_min_confidence = getattr(
            weak_mark_params, "weak_fill_auto_resolve_min_confidence", 0.8
        )
        review_min_confidence = getattr(
            weak_mark_params, "weak_fill_review_min_confidence", 0.65
        )

        if confidence >= auto_min_confidence:
            return "RESOLVED_CANDIDATE"
        if confidence >= review_min_confidence:
            return "NEEDS_REVIEW"
        return None

    def append_single_choice_conflict_review(
        self, field_label, original_value, candidate, diagnostics, status
    ):
        """Store one single-choice conflict candidate for auxiliary review outputs."""
        confidence = self.get_single_choice_conflict_confidence(diagnostics)
        self.last_weak_fill_reviews.append(
            {
                "review_type": "SINGLE_CHOICE_CONFLICT_REVIEW",
                "field": field_label,
                "original_value": original_value,
                "candidate": candidate,
                "status": status,
                "confidence": confidence,
                "score": confidence * 5.0,
                "reason": "single_choice_conflict",
                "legacy_rejection": "",
                "evidence": "gap,delta_from_blank",
                "ambiguity": 1.0 - confidence,
                "density_gap": 0.0,
                "center_density": 0.0,
                "center_edge_ratio": 0.0,
                "threshold_vote_ratio": 0.0,
                "multiscale_stability": 0.0,
            }
        )

    def append_identifier_review(
        self, field_label, candidate, diagnostics, status, legacy_rejection=""
    ):
        """Store one weak identifier candidate for auxiliary review outputs."""
        confidence = self.get_identifier_review_confidence(diagnostics)
        self.last_weak_fill_reviews.append(
            {
                "review_type": "ID_REVIEW",
                "field": field_label,
                "original_value": "",
                "candidate": candidate,
                "status": status,
                "confidence": confidence,
                "score": confidence * 5.0,
                "reason": "weak_identifier_candidate",
                "legacy_rejection": legacy_rejection,
                "evidence": "gap,delta_from_blank,page_z,density_gap",
                "ambiguity": 1.0 - confidence,
                "density_gap": diagnostics.get("density_gap", 0.0),
                "center_density": diagnostics.get("darkest_center_density", 0.0),
                "center_edge_ratio": diagnostics.get("darkest_center_edge_ratio", 0.0),
                "threshold_vote_ratio": 0.0,
                "multiscale_stability": 0.0,
            }
        )

    def observe_single_choice_conflict_review(
        self, field_block, field_block_bubbles, q_strip_vals, detected_bubbles
    ):
        """Record a single-choice conflict review without changing detected bubbles."""
        weak_mark_params = self.tuning_config.weak_mark_params
        if getattr(weak_mark_params, "resolve_single_choice_conflicts", False):
            return detected_bubbles

        if field_block.multi_select:
            return detected_bubbles

        if field_block.field_type not in weak_mark_params.supported_field_types:
            return detected_bubbles

        if len(detected_bubbles) <= 1:
            return detected_bubbles

        field_label = field_block_bubbles[0].field_label
        if field_label in weak_mark_params.exclude_labels:
            return detected_bubbles

        diagnostics = self.get_field_diagnostics(q_strip_vals)
        darkest_bubble = field_block_bubbles[diagnostics["darkest_index"]]
        self.append_single_choice_conflict_review(
            field_label,
            "".join(b.field_value for b in detected_bubbles),
            darkest_bubble.field_value,
            diagnostics,
            "REVIEW",
        )
        return detected_bubbles

    def get_weak_marked_bubble(
        self, field_block, field_block_bubbles, q_strip_vals, image, page_blank_model
    ):
        """Return a conservative weak-mark fallback bubble, or None.

        The normal thresholding pass is the source of truth. This fallback is
        only meant for blank single-choice responses where one option is still
        noticeably darker than the rest, but not dark enough to cross the
        regular local/global threshold.
        """
        weak_mark_params = self.tuning_config.weak_mark_params
        if not weak_mark_params.enabled:
            return None

        if field_block.field_type not in weak_mark_params.supported_field_types:
            return None

        if len(field_block_bubbles) < 2:
            return None

        # Avoid applying single-choice fallback to configured multi-select or
        # other known-sensitive fields.
        field_label = field_block_bubbles[0].field_label
        if field_block.multi_select:
            return None

        if field_label in weak_mark_params.exclude_labels:
            return None

        diagnostics = self.get_field_diagnostics(q_strip_vals)
        diagnostics = self.enrich_diagnostics_with_density(
            image, field_block, field_block_bubbles, q_strip_vals, diagnostics, page_blank_model
        )
        darkest_index = diagnostics["darkest_index"]
        darkest_mean = diagnostics["darkest_mean"]
        second_darkest_mean = diagnostics["second_darkest_mean"]
        gap = diagnostics["gap"]
        blank_baseline = diagnostics["blank_baseline"]
        delta_from_blank = diagnostics["delta_from_blank"]

        rejection_reason = None
        if darkest_mean > weak_mark_params.max_mean:
            rejection_reason = "max_mean"
        elif delta_from_blank < weak_mark_params.adaptive_min_delta_from_blank:
            rejection_reason = "adaptive_min_delta_from_blank"
        else:
            density_supported = (
                diagnostics["darkest_density"] >= weak_mark_params.min_dark_pixel_ratio
                and diagnostics["density_gap"] >= weak_mark_params.min_density_gap
            )
            strong_mean_supported = gap >= weak_mark_params.min_gap * 1.5
            page_supported = diagnostics["page_z_score"] >= weak_mark_params.min_page_z_score
            gap_supported = gap >= weak_mark_params.min_gap
            strict_delta_supported = delta_from_blank >= weak_mark_params.min_delta_from_blank
            if not (
                (strict_delta_supported and gap_supported)
                or density_supported
                or strong_mean_supported
                or page_supported
            ):
                rejection_reason = "support"

        if rejection_reason is not None:
            score_decision = self.get_single_choice_weak_fill_decision(diagnostics)
            if score_decision["status"] != "EMPTY":
                restore_status = self.get_weak_fill_review_restore_status(
                    score_decision, diagnostics
                )
                review_decision = score_decision
                if restore_status is not None:
                    review_decision = {**score_decision, "status": restore_status}
                self.append_weak_fill_review(
                    field_label,
                    field_block_bubbles[darkest_index].field_value,
                    review_decision,
                    diagnostics,
                    rejection_reason,
                )
                logger.warning(
                    f"Weak mark candidate review: field '{field_label}' "
                    f"candidate='{field_block_bubbles[darkest_index].field_value}' "
                    f"status={review_decision['status']} "
                    f"score={score_decision['score']:.2f} "
                    f"reason={score_decision['reason']} "
                    f"legacy_rejection={rejection_reason} "
                    f"evidence={','.join(score_decision.get('evidence', []))} "
                    f"ambiguity={score_decision.get('ambiguity', 0.0):.2f} "
                    f"darkest_mean={darkest_mean:.2f}, "
                    f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                    f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                    f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
                    f"page_z={diagnostics['page_z_score']:.2f}, "
                    f"dark_ratio={diagnostics['darkest_dark_ratio']:.3f}, "
                    f"center_density={diagnostics['darkest_center_density']:.3f}, "
                    f"edge_density={diagnostics['darkest_edge_density']:.3f}, "
                    f"center_edge_ratio={diagnostics['darkest_center_edge_ratio']:.3f}, "
                    f"density={diagnostics['darkest_density']:.3f}, "
                    f"density_gap={diagnostics['density_gap']:.3f}, "
                    f"threshold_vote_count={diagnostics['threshold_vote_count']}, "
                    f"threshold_vote_ratio={diagnostics['threshold_vote_ratio']:.3f}, "
                    f"threshold_density_gaps="
                    f"{','.join(f'{gap:.3f}' for gap in diagnostics['threshold_density_gaps'])}, "
                    f"multiscale_vote_count={diagnostics['multiscale_vote_count']}, "
                    f"multiscale_stability={diagnostics['multiscale_stability']:.3f}, "
                    f"multiscale_density_gaps="
                    f"{','.join(f'{gap:.3f}' for gap in diagnostics['multiscale_density_gaps'])}"
                )
                if restore_status is not None:
                    return field_block_bubbles[darkest_index]

            logger.info(
                f"Weak mark candidate rejected: field '{field_label}' "
                f"reason={rejection_reason} darkest_mean={darkest_mean:.2f}, "
                f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                f"page_z={diagnostics['page_z_score']:.2f}, "
                f"density={diagnostics['darkest_density']:.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f}"
            )
            return None

        weak_bubble = field_block_bubbles[darkest_index]
        logger.warning(
            f"Weak mark fallback: field '{field_label}' -> "
            f"'{weak_bubble.field_value}' "
            f"(darkest_mean={darkest_mean:.2f}, "
            f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
            f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
            f"page_blank_mean={diagnostics['page_blank_mean']:.2f}, "
            f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
            f"page_z={diagnostics['page_z_score']:.2f}, "
            f"density={diagnostics['darkest_density']:.3f}, "
            f"density_gap={diagnostics['density_gap']:.3f}, "
            f"threshold_vote_count={diagnostics['threshold_vote_count']}, "
            f"threshold_vote_ratio={diagnostics['threshold_vote_ratio']:.3f}, "
            f"multiscale_vote_count={diagnostics['multiscale_vote_count']}, "
            f"multiscale_stability={diagnostics['multiscale_stability']:.3f})"
        )
        return weak_bubble

    def resolve_single_choice_conflict(
        self, field_block, field_block_bubbles, q_strip_vals, detected_bubbles
    ):
        """Resolve impossible multi-mark output for non-multiSelect single-choice fields.

        Multi-select questions are intentionally excluded. For normal single-choice
        fields, outputting ABCD is structurally invalid. When the main threshold
        marks multiple options, keep the darkest candidate only if it is at least
        directionally darker than the rest; otherwise keep the field blank for
        review instead of returning a false multi-select answer.
        """
        weak_mark_params = self.tuning_config.weak_mark_params
        if not getattr(weak_mark_params, "resolve_single_choice_conflicts", False):
            return detected_bubbles

        if field_block.multi_select:
            return detected_bubbles

        if field_block.field_type not in weak_mark_params.supported_field_types:
            return detected_bubbles

        if len(detected_bubbles) <= 1:
            return detected_bubbles

        field_label = field_block_bubbles[0].field_label
        if field_label in weak_mark_params.exclude_labels:
            return detected_bubbles

        diagnostics = self.get_field_diagnostics(q_strip_vals)
        darkest_index = diagnostics["darkest_index"]
        darkest_bubble = field_block_bubbles[darkest_index]
        gap = diagnostics["gap"]
        delta_from_blank = diagnostics["delta_from_blank"]

        confidence = self.get_single_choice_conflict_confidence(diagnostics)
        auto_resolve_min_confidence = getattr(
            weak_mark_params, "conflict_auto_resolve_min_confidence", 0.8
        )
        review_min_confidence = getattr(
            weak_mark_params, "conflict_review_min_confidence", 0.65
        )

        if confidence >= auto_resolve_min_confidence:
            status = "RESOLVED_CANDIDATE"
        elif confidence >= review_min_confidence:
            status = "NEEDS_REVIEW"
        else:
            status = "LOW_CONFIDENCE"

        if status in {"RESOLVED_CANDIDATE", "NEEDS_REVIEW"}:
            logger.warning(
                f"Single-choice conflict resolved: field '{field_label}' "
                f"{''.join(b.field_value for b in detected_bubbles)} -> "
                f"'{darkest_bubble.field_value}' "
                f"status={status} confidence={confidence:.3f} "
                f"(darkest_mean={diagnostics['darkest_mean']:.2f}, "
                f"second_darkest_mean={diagnostics['second_darkest_mean']:.2f}, "
                f"gap={gap:.2f}, blank_baseline={diagnostics['blank_baseline']:.2f}, "
                f"delta={delta_from_blank:.2f})"
            )
            self.append_single_choice_conflict_review(
                field_label,
                "".join(b.field_value for b in detected_bubbles),
                darkest_bubble.field_value,
                diagnostics,
                status,
            )
            return [darkest_bubble]

        logger.warning(
            f"Single-choice conflict unresolved: field '{field_label}' "
            f"{''.join(b.field_value for b in detected_bubbles)} -> blank "
            f"status={status} confidence={confidence:.3f} "
            f"(darkest_mean={diagnostics['darkest_mean']:.2f}, "
            f"second_darkest_mean={diagnostics['second_darkest_mean']:.2f}, "
            f"gap={gap:.2f}, blank_baseline={diagnostics['blank_baseline']:.2f}, "
            f"delta={delta_from_blank:.2f})"
        )
        self.append_single_choice_conflict_review(
            field_label,
            "".join(b.field_value for b in detected_bubbles),
            darkest_bubble.field_value,
            diagnostics,
            status,
        )
        return []

    def get_weak_identifier_bubble(
        self, field_block, field_block_bubbles, q_strip_vals, detected_bubbles, image, page_blank_model
    ):
        """Return a conservative weak identifier fallback bubble, or None.

        Identifier digits have ten candidates and are more sensitive than answer
        fields because a false positive changes the student's identity. Keep this
        separate from the answer weak-mark fallback and require both a local
        blank-baseline gap and a second-darkest gap.
        """
        weak_identifier_params = self.tuning_config.weak_identifier_params
        if not weak_identifier_params.enabled:
            return None

        if field_block.field_type not in weak_identifier_params.supported_field_types:
            return None

        if field_block.direction != "vertical":
            return None

        if detected_bubbles:
            return None

        if not field_block_bubbles or len(field_block_bubbles) < 3:
            return None

        field_label = field_block_bubbles[0].field_label
        configured_labels = weak_identifier_params.labels
        if configured_labels and field_label not in configured_labels:
            return None

        if field_label in weak_identifier_params.exclude_labels:
            return None

        diagnostics = self.get_field_diagnostics(q_strip_vals)
        diagnostics = self.enrich_diagnostics_with_density(
            image, field_block, field_block_bubbles, q_strip_vals, diagnostics, page_blank_model
        )
        darkest_index = diagnostics["darkest_index"]
        darkest_mean = diagnostics["darkest_mean"]
        second_darkest_mean = diagnostics["second_darkest_mean"]
        gap = diagnostics["gap"]
        blank_baseline = diagnostics["blank_baseline"]
        delta_from_blank = diagnostics["delta_from_blank"]

        strict_mean_rule = (
            gap >= weak_identifier_params.min_gap
            and delta_from_blank >= weak_identifier_params.min_delta_from_blank
        )
        adaptive_rule = (
            gap >= weak_identifier_params.adaptive_min_gap
            and delta_from_blank >= weak_identifier_params.adaptive_min_delta_from_blank
            and diagnostics["page_z_score"] >= weak_identifier_params.min_page_z_score
            and diagnostics["darkest_density"] >= weak_identifier_params.min_dark_pixel_ratio
            and diagnostics["density_gap"] >= weak_identifier_params.min_density_gap
        )
        if darkest_mean > weak_identifier_params.adaptive_max_mean:
            self.append_identifier_review(
                field_label,
                field_block_bubbles[darkest_index].field_value,
                diagnostics,
                "LOW_CONFIDENCE",
                "adaptive_max_mean",
            )
            logger.info(
                f"Weak identifier candidate rejected: field '{field_label}' "
                f"reason=adaptive_max_mean darkest_mean={darkest_mean:.2f}, "
                f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
                f"page_z={diagnostics['page_z_score']:.2f}, "
                f"density={diagnostics['darkest_density']:.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f}"
            )
            return None

        if darkest_mean > weak_identifier_params.max_mean and not adaptive_rule:
            self.append_identifier_review(
                field_label,
                field_block_bubbles[darkest_index].field_value,
                diagnostics,
                "LOW_CONFIDENCE",
                "max_mean_without_adaptive_support",
            )
            logger.info(
                f"Weak identifier candidate rejected: field '{field_label}' "
                f"reason=max_mean_without_adaptive_support darkest_mean={darkest_mean:.2f}, "
                f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
                f"page_z={diagnostics['page_z_score']:.2f}, "
                f"density={diagnostics['darkest_density']:.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f}"
            )
            return None

        if not (strict_mean_rule or adaptive_rule):
            self.append_identifier_review(
                field_label,
                field_block_bubbles[darkest_index].field_value,
                diagnostics,
                "LOW_CONFIDENCE",
                "support",
            )
            logger.info(
                f"Weak identifier candidate rejected: field '{field_label}' "
                f"reason=support darkest_mean={darkest_mean:.2f}, "
                f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
                f"page_z={diagnostics['page_z_score']:.2f}, "
                f"density={diagnostics['darkest_density']:.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f}"
            )
            return None

        weak_bubble = field_block_bubbles[darkest_index]
        self.append_identifier_review(
            field_label,
            weak_bubble.field_value,
            diagnostics,
            "RESOLVED_CANDIDATE",
        )
        logger.warning(
            f"Weak identifier fallback: field '{field_label}' -> "
            f"'{weak_bubble.field_value}' "
            f"(darkest_mean={darkest_mean:.2f}, "
            f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
            f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
            f"page_blank_mean={diagnostics['page_blank_mean']:.2f}, "
            f"page_z={diagnostics['page_z_score']:.2f}, "
            f"density={diagnostics['darkest_density']:.3f}, "
            f"density_gap={diagnostics['density_gap']:.3f}, "
            f"rule={'strict' if strict_mean_rule else 'adaptive'})"
        )
        return weak_bubble

    def get_weak_multi_marked_bubbles(
        self, field_block_bubbles, q_strip_vals, detected_bubbles
    ):
        """Return conservative weak multi-select candidates to append."""
        weak_multi_params = self.tuning_config.weak_multi_mark_params
        if not weak_multi_params.enabled:
            return []

        if not field_block_bubbles:
            return []

        field_label = field_block_bubbles[0].field_label
        if not self.is_weak_multi_label_allowed(field_block_bubbles):
            return []

        detected_values = {bubble.field_value for bubble in detected_bubbles}
        if weak_multi_params.only_when_blank and detected_values:
            return []

        if len(detected_values) >= weak_multi_params.max_marks:
            return []

        # Estimate blank background from the lighter half of the options. This
        # keeps the baseline local to the question and avoids global threshold
        # drift on lightly filled rows.
        sorted_vals = sorted(q_strip_vals)
        lighter_half = sorted_vals[len(sorted_vals) // 2 :]
        blank_baseline = float(np.mean(lighter_half))

        weak_bubbles = []
        for bubble, mean_value in zip(field_block_bubbles, q_strip_vals):
            if bubble.field_value in detected_values:
                continue
            if len(detected_values) + len(weak_bubbles) >= weak_multi_params.max_marks:
                break
            delta_from_blank = blank_baseline - mean_value
            if mean_value > weak_multi_params.max_mean:
                continue
            if delta_from_blank < weak_multi_params.min_delta_from_blank:
                continue
            weak_bubbles.append(bubble)
            logger.warning(
                f"Weak multi-mark fallback: field '{field_label}' -> "
                f"append '{bubble.field_value}' "
                f"(mean={mean_value:.2f}, blank_baseline={blank_baseline:.2f}, "
                f"delta={delta_from_blank:.2f})"
            )

        return weak_bubbles

    def is_weak_multi_label_allowed(self, field_block_bubbles):
        weak_multi_params = self.tuning_config.weak_multi_mark_params
        field_label = field_block_bubbles[0].field_label
        configured_labels = weak_multi_params.labels
        return field_label in configured_labels or (
            len(configured_labels) == 0 and field_block_bubbles[0].multi_select
        )

    def get_weak_multi_full_select_bubbles(
        self, field_block_bubbles, q_strip_vals, detected_bubbles, page_blank_baseline
    ):
        """Return all options for weakly filled full-select multi-choice rows.

        This fallback handles valid multi-select questions where every option is
        filled. In that case the lighter-half blank baseline used by
        get_weak_multi_marked_bubbles is not reliable because there may be no
        blank option in the row.
        """
        weak_multi_params = self.tuning_config.weak_multi_mark_params
        if not weak_multi_params.enabled:
            return []

        if not weak_multi_params.full_select_fallback_enabled:
            return []

        if not field_block_bubbles:
            return []

        field_label = field_block_bubbles[0].field_label
        if not self.is_weak_multi_label_allowed(field_block_bubbles):
            return []

        if detected_bubbles:
            return []

        if len(field_block_bubbles) > weak_multi_params.max_marks:
            return []

        max_mean = max(q_strip_vals)
        spread = max(q_strip_vals) - min(q_strip_vals)
        delta_from_page_blank = page_blank_baseline - max_mean
        if max_mean > weak_multi_params.full_select_max_mean:
            return []

        if delta_from_page_blank < weak_multi_params.full_select_min_delta_from_blank:
            return []

        if spread > weak_multi_params.full_select_max_spread:
            return []

        logger.warning(
            f"Weak multi full-select fallback: field '{field_label}' -> "
            f"'{''.join(bubble.field_value for bubble in field_block_bubbles)}' "
            f"(max_mean={max_mean:.2f}, page_blank_baseline={page_blank_baseline:.2f}, "
            f"delta_from_page_blank={delta_from_page_blank:.2f}, spread={spread:.2f})"
        )
        return list(field_block_bubbles)

    def read_omr_response(self, template, image, name, save_dir=None):
        config = self.tuning_config
        auto_align = config.alignment_params.auto_align
        try:
            img = image.copy()
            # origDim = img.shape[:2]
            img = ImageUtils.resize_util(
                img, template.page_dimensions[0], template.page_dimensions[1]
            )
            if img.max() > img.min():
                img = ImageUtils.normalize_util(img)
            # Processing copies
            transp_layer = img.copy()
            final_marked = img.copy()

            morph = img.copy()
            self.append_save_img(3, morph)

            if auto_align:
                # Note: clahe is good for morphology, bad for thresholding
                morph = CLAHE_HELPER.apply(morph)
                self.append_save_img(3, morph)
                # Remove shadows further, make columns/boxes darker (less gamma)
                morph = ImageUtils.adjust_gamma(
                    morph, config.threshold_params.GAMMA_LOW
                )
                # TODO: all numbers should come from either constants or config
                _, morph = cv2.threshold(morph, 220, 220, cv2.THRESH_TRUNC)
                morph = ImageUtils.normalize_util(morph)
                self.append_save_img(3, morph)
                if config.outputs.show_image_level >= 4:
                    InteractionUtils.show("morph1", morph, 0, 1, config)

            # Move them to data class if needed
            # Overlay Transparencies
            alpha = 0.65
            omr_response = {}
            self.last_weak_fill_reviews = []
            self.last_ocr_results = {}
            multi_marked, multi_roll = False, False

            # TODO Make this part useful for visualizing status checks
            # blackVals=[0]
            # whiteVals=[255]

            if config.outputs.show_image_level >= 5:
                all_c_box_vals = {"int": [], "mcq": []}
                # TODO: simplify this logic
                q_nums = {"int": [], "mcq": []}

            # Find Shifts for the field_blocks --> Before calculating threshold!
            if auto_align:
                # print("Begin Alignment")
                # Open : erode then dilate
                v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 10))
                morph_v = cv2.morphologyEx(
                    morph, cv2.MORPH_OPEN, v_kernel, iterations=3
                )
                _, morph_v = cv2.threshold(morph_v, 200, 200, cv2.THRESH_TRUNC)
                morph_v = 255 - ImageUtils.normalize_util(morph_v)

                if config.outputs.show_image_level >= 3:
                    InteractionUtils.show(
                        "morphed_vertical", morph_v, 0, 1, config=config
                    )

                # InteractionUtils.show("morph1",morph,0,1,config=config)
                # InteractionUtils.show("morphed_vertical",morph_v,0,1,config=config)

                self.append_save_img(3, morph_v)

                morph_thr = 60  # for Mobile images, 40 for scanned Images
                _, morph_v = cv2.threshold(morph_v, morph_thr, 255, cv2.THRESH_BINARY)
                # kernel best tuned to 5x5 now
                morph_v = cv2.erode(morph_v, np.ones((5, 5), np.uint8), iterations=2)

                self.append_save_img(3, morph_v)
                # h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 2))
                # morph_h = cv2.morphologyEx(morph, cv2.MORPH_OPEN, h_kernel, iterations=3)
                # ret, morph_h = cv2.threshold(morph_h,200,200,cv2.THRESH_TRUNC)
                # morph_h = 255 - normalize_util(morph_h)
                # InteractionUtils.show("morph_h",morph_h,0,1,config=config)
                # _, morph_h = cv2.threshold(morph_h,morph_thr,255,cv2.THRESH_BINARY)
                # morph_h = cv2.erode(morph_h,  np.ones((5,5),np.uint8), iterations = 2)
                if config.outputs.show_image_level >= 3:
                    InteractionUtils.show(
                        "morph_thr_eroded", morph_v, 0, 1, config=config
                    )

                self.append_save_img(6, morph_v)

                # template relative alignment code
                for field_block in template.field_blocks:
                    s, d = field_block.origin, field_block.dimensions

                    match_col, max_steps, align_stride, thk = map(
                        config.alignment_params.get,
                        [
                            "match_col",
                            "max_steps",
                            "stride",
                            "thickness",
                        ],
                    )
                    shift, steps = 0, 0
                    while steps < max_steps:
                        left_mean = np.mean(
                            morph_v[
                                s[1] : s[1] + d[1],
                                s[0] + shift - thk : -thk + s[0] + shift + match_col,
                            ]
                        )
                        right_mean = np.mean(
                            morph_v[
                                s[1] : s[1] + d[1],
                                s[0]
                                + shift
                                - match_col
                                + d[0]
                                + thk : thk
                                + s[0]
                                + shift
                                + d[0],
                            ]
                        )

                        # For demonstration purposes-
                        # if(field_block.name == "int1"):
                        #     ret = morph_v.copy()
                        #     cv2.rectangle(ret,
                        #                   (s[0]+shift-thk,s[1]),
                        #                   (s[0]+shift+thk+d[0],s[1]+d[1]),
                        #                   CLR_WHITE,
                        #                   3)
                        #     appendSaveImg(6,ret)
                        # print(shift, left_mean, right_mean)
                        left_shift, right_shift = left_mean > 100, right_mean > 100
                        if left_shift:
                            if right_shift:
                                break
                            else:
                                shift -= align_stride
                        else:
                            if right_shift:
                                shift += align_stride
                            else:
                                break
                        steps += 1

                    field_block.shift = shift
                    # print("Aligned field_block: ",field_block.name,"Corrected Shift:",
                    #   field_block.shift,", dimensions:", field_block.dimensions,
                    #   "origin:", field_block.origin,'\n')
                # print("End Alignment")

            final_align = None
            if config.outputs.show_image_level >= 2:
                initial_align = self.draw_template_layout(img, template, shifted=False)
                final_align = self.draw_template_layout(
                    img, template, shifted=True, draw_qvals=True
                )
                # appendSaveImg(4,mean_vals)
                self.append_save_img(2, initial_align)
                self.append_save_img(2, final_align)

                if auto_align:
                    final_align = np.hstack((initial_align, final_align))
            self.append_save_img(5, img)

            # Get mean bubbleValues n other stats
            all_q_vals, all_q_strip_arrs, all_q_std_vals = [], [], []
            total_q_strip_no = 0
            for field_block in template.field_blocks:
                if field_block.engine == "paddleocr":
                    field_label, text = self.read_ocr_response(img, field_block)
                    omr_response[field_label] = text
                    continue

                box_w, box_h = field_block.bubble_dimensions
                q_std_vals = []
                for field_block_bubbles in field_block.traverse_bubbles:
                    q_strip_vals = []
                    for pt in field_block_bubbles:
                        # shifted
                        x, y = (pt.x + field_block.shift, pt.y)
                        rect = [y, y + box_h, x, x + box_w]
                        q_strip_vals.append(
                            cv2.mean(img[rect[0] : rect[1], rect[2] : rect[3]])[0]
                            # detectCross(img, rect) ? 100 : 0
                        )
                    q_std_vals.append(round(np.std(q_strip_vals), 2))
                    all_q_strip_arrs.append(q_strip_vals)
                    # _, _, _ = get_global_threshold(q_strip_vals, "QStrip Plot",
                    #   plot_show=False, sort_in_plot=True)
                    # hist = getPlotImg()
                    # InteractionUtils.show("QStrip "+field_block_bubbles[0].field_label, hist, 0, 1,config=config)
                    all_q_vals.extend(q_strip_vals)
                    # print(total_q_strip_no, field_block_bubbles[0].field_label, q_std_vals[len(q_std_vals)-1])
                    total_q_strip_no += 1
                all_q_std_vals.extend(q_std_vals)

            if all_q_vals:
                global_std_thresh, _, _ = self.get_global_threshold(
                    all_q_std_vals
                )  # , "Q-wise Std-dev Plot", plot_show=True, sort_in_plot=True)
            else:
                global_std_thresh = 0.0
            # plt.show()
            # hist = getPlotImg()
            # InteractionUtils.show("StdHist", hist, 0, 1,config=config)

            # Note: Plotting takes Significant times here --> Change Plotting args
            # to support show_image_level
            # , "Mean Intensity Histogram",plot_show=True, sort_in_plot=True)
            if all_q_vals:
                global_thr, _, _ = self.get_global_threshold(all_q_vals, looseness=4)
            else:
                global_thr = 255.0
            page_blank_model = self.get_page_blank_model(all_q_vals)
            page_blank_baseline = page_blank_model["mean"]

            logger.info(
                f"Thresholding: \tglobal_thr: {round(global_thr, 2)} \tglobal_std_THR: {round(global_std_thresh, 2)}\t{'(Looks like a Xeroxed OMR)' if (global_thr == 255) else ''}"
            )
            # plt.show()
            # hist = getPlotImg()
            # InteractionUtils.show("StdHist", hist, 0, 1,config=config)

            # if(config.outputs.show_image_level>=1):
            #     hist = getPlotImg()
            #     InteractionUtils.show("Hist", hist, 0, 1,config=config)
            #     appendSaveImg(4,hist)
            #     appendSaveImg(5,hist)
            #     appendSaveImg(2,hist)

            per_omr_threshold_avg, total_q_strip_no, total_q_box_no = 0, 0, 0
            for field_block in template.field_blocks:
                if field_block.engine == "paddleocr":
                    continue

                block_q_strip_no = 1
                box_w, box_h = field_block.bubble_dimensions
                shift = field_block.shift
                s, d = field_block.origin, field_block.dimensions
                key = field_block.name[:3]
                # cv2.rectangle(final_marked,(s[0]+shift,s[1]),(s[0]+shift+d[0],
                #   s[1]+d[1]),CLR_BLACK,3)
                for field_block_bubbles in field_block.traverse_bubbles:
                    # All Black or All White case
                    no_outliers = all_q_std_vals[total_q_strip_no] < global_std_thresh
                    # print(total_q_strip_no, field_block_bubbles[0].field_label,
                    #   all_q_std_vals[total_q_strip_no], "no_outliers:", no_outliers)
                    per_q_strip_threshold = self.get_local_threshold(
                        all_q_strip_arrs[total_q_strip_no],
                        global_thr,
                        no_outliers,
                        f"Mean Intensity Histogram for {key}.{field_block_bubbles[0].field_label}.{block_q_strip_no}",
                        config.outputs.show_image_level >= 6,
                    )
                    # print(field_block_bubbles[0].field_label,key,block_q_strip_no, "THR: ",
                    #   round(per_q_strip_threshold,2))
                    per_omr_threshold_avg += per_q_strip_threshold

                    # Note: Little debugging visualization - view the particular Qstrip
                    # if(
                    #     0
                    #     # or "q17" in (field_block_bubbles[0].field_label)
                    #     # or (field_block_bubbles[0].field_label+str(block_q_strip_no))=="q15"
                    #  ):
                    #     st, end = qStrip
                    #     InteractionUtils.show("QStrip: "+key+"-"+str(block_q_strip_no),
                    #     img[st[1] : end[1], st[0]+shift : end[0]+shift],0,config=config)

                    # TODO: get rid of total_q_box_no
                    detected_bubbles = []
                    for bubble in field_block_bubbles:
                        bubble_is_marked = (
                            per_q_strip_threshold > all_q_vals[total_q_box_no]
                        )
                        total_q_box_no += 1
                        if bubble_is_marked:
                            detected_bubbles.append(bubble)
                            x, y, field_value = (
                                bubble.x + field_block.shift,
                                bubble.y,
                                bubble.field_value,
                            )
                            cv2.rectangle(
                                final_marked,
                                (int(x + box_w / 12), int(y + box_h / 12)),
                                (
                                    int(x + box_w - box_w / 12),
                                    int(y + box_h - box_h / 12),
                                ),
                                CLR_DARK_GRAY,
                                3,
                            )

                            cv2.putText(
                                final_marked,
                                str(field_value),
                                (x, y),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                TEXT_SIZE,
                                (20, 20, 10),
                                int(1 + 3.5 * TEXT_SIZE),
                            )
                        else:
                            cv2.rectangle(
                                final_marked,
                                (int(x + box_w / 10), int(y + box_h / 10)),
                                (
                                    int(x + box_w - box_w / 10),
                                    int(y + box_h - box_h / 10),
                                ),
                                CLR_GRAY,
                                -1,
                            )

                    detected_bubbles = self.observe_single_choice_conflict_review(
                        field_block,
                        field_block_bubbles,
                        all_q_strip_arrs[total_q_strip_no],
                        detected_bubbles,
                    )
                    detected_bubbles = self.resolve_single_choice_conflict(
                        field_block,
                        field_block_bubbles,
                        all_q_strip_arrs[total_q_strip_no],
                        detected_bubbles,
                    )

                    for bubble in detected_bubbles:
                        field_label, field_value = (
                            bubble.field_label,
                            bubble.field_value,
                        )
                        # Only send rolls multi-marked in the directory
                        multi_marked_local = field_label in omr_response
                        omr_response[field_label] = (
                            (omr_response[field_label] + field_value)
                            if multi_marked_local
                            else field_value
                        )
                        # TODO: generalize this into identifier
                        # multi_roll = multi_marked_local and "Roll" in str(q)
                        multi_marked = multi_marked or multi_marked_local

                    weak_multi_bubbles = self.get_weak_multi_marked_bubbles(
                        field_block_bubbles,
                        all_q_strip_arrs[total_q_strip_no],
                        detected_bubbles,
                    )
                    for weak_bubble in weak_multi_bubbles:
                        field_label, field_value = (
                            weak_bubble.field_label,
                            weak_bubble.field_value,
                        )
                        omr_response[field_label] = (
                            omr_response[field_label] + field_value
                            if field_label in omr_response
                            else field_value
                        )
                        multi_marked = True
                        x, y = (
                            weak_bubble.x + field_block.shift,
                            weak_bubble.y,
                        )
                        cv2.rectangle(
                            final_marked,
                            (int(x + box_w / 12), int(y + box_h / 12)),
                            (
                                int(x + box_w - box_w / 12),
                                int(y + box_h - box_h / 12),
                            ),
                            CLR_DARK_GRAY,
                            3,
                        )
                        cv2.putText(
                            final_marked,
                            str(field_value),
                            (x, y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            TEXT_SIZE,
                            (20, 20, 10),
                            int(1 + 3.5 * TEXT_SIZE),
                        )

                    weak_multi_full_select_bubbles = []
                    if len(detected_bubbles) == 0 and len(weak_multi_bubbles) == 0:
                        weak_multi_full_select_bubbles = (
                            self.get_weak_multi_full_select_bubbles(
                                field_block_bubbles,
                                all_q_strip_arrs[total_q_strip_no],
                                detected_bubbles,
                                page_blank_baseline,
                            )
                        )
                        for weak_bubble in weak_multi_full_select_bubbles:
                            field_label, field_value = (
                                weak_bubble.field_label,
                                weak_bubble.field_value,
                            )
                            omr_response[field_label] = (
                                omr_response[field_label] + field_value
                                if field_label in omr_response
                                else field_value
                            )
                            multi_marked = True
                            x, y = (
                                weak_bubble.x + field_block.shift,
                                weak_bubble.y,
                            )
                            cv2.rectangle(
                                final_marked,
                                (int(x + box_w / 12), int(y + box_h / 12)),
                                (
                                    int(x + box_w - box_w / 12),
                                    int(y + box_h - box_h / 12),
                                ),
                                CLR_DARK_GRAY,
                                3,
                            )
                            cv2.putText(
                                final_marked,
                                str(field_value),
                                (x, y),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                TEXT_SIZE,
                                (20, 20, 10),
                                int(1 + 3.5 * TEXT_SIZE),
                            )

                    if (
                        len(detected_bubbles) == 0
                        and len(weak_multi_bubbles) == 0
                        and len(weak_multi_full_select_bubbles) == 0
                    ):
                        weak_bubble = self.get_weak_marked_bubble(
                            field_block,
                            field_block_bubbles,
                            all_q_strip_arrs[total_q_strip_no],
                            img,
                            page_blank_model,
                        )
                        if weak_bubble is not None:
                            field_label, field_value = (
                                weak_bubble.field_label,
                                weak_bubble.field_value,
                            )
                            omr_response[field_label] = field_value
                            x, y = (
                                weak_bubble.x + field_block.shift,
                                weak_bubble.y,
                            )
                            cv2.rectangle(
                                final_marked,
                                (int(x + box_w / 12), int(y + box_h / 12)),
                                (
                                    int(x + box_w - box_w / 12),
                                    int(y + box_h - box_h / 12),
                                ),
                                CLR_DARK_GRAY,
                                3,
                            )
                            cv2.putText(
                                final_marked,
                                str(field_value),
                                (x, y),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                TEXT_SIZE,
                                (20, 20, 10),
                                int(1 + 3.5 * TEXT_SIZE),
                            )
                        else:
                            weak_identifier_bubble = self.get_weak_identifier_bubble(
                                field_block,
                                field_block_bubbles,
                                all_q_strip_arrs[total_q_strip_no],
                                detected_bubbles,
                                img,
                                page_blank_model,
                            )
                            if weak_identifier_bubble is not None:
                                field_label, field_value = (
                                    weak_identifier_bubble.field_label,
                                    weak_identifier_bubble.field_value,
                                )
                                omr_response[field_label] = field_value
                                x, y = (
                                    weak_identifier_bubble.x + field_block.shift,
                                    weak_identifier_bubble.y,
                                )
                                cv2.rectangle(
                                    final_marked,
                                    (int(x + box_w / 12), int(y + box_h / 12)),
                                    (
                                        int(x + box_w - box_w / 12),
                                        int(y + box_h - box_h / 12),
                                    ),
                                    CLR_DARK_GRAY,
                                    3,
                                )
                                cv2.putText(
                                    final_marked,
                                    str(field_value),
                                    (x, y),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    TEXT_SIZE,
                                    (20, 20, 10),
                                    int(1 + 3.5 * TEXT_SIZE),
                                )
                            else:
                                field_label = field_block_bubbles[0].field_label
                                omr_response[field_label] = field_block.empty_val

                    if config.outputs.show_image_level >= 5:
                        if key in all_c_box_vals:
                            q_nums[key].append(f"{key[:2]}_c{str(block_q_strip_no)}")
                            all_c_box_vals[key].append(
                                all_q_strip_arrs[total_q_strip_no]
                            )

                    block_q_strip_no += 1
                    total_q_strip_no += 1
                # /for field_block

            per_omr_threshold_avg = (
                per_omr_threshold_avg / total_q_strip_no if total_q_strip_no else 0.0
            )
            per_omr_threshold_avg = round(per_omr_threshold_avg, 2)
            # Translucent
            cv2.addWeighted(
                final_marked, alpha, transp_layer, 1 - alpha, 0, final_marked
            )
            # Box types
            if config.outputs.show_image_level >= 6:
                # plt.draw()
                f, axes = plt.subplots(len(all_c_box_vals), sharey=True)
                f.canvas.manager.set_window_title(name)
                ctr = 0
                type_name = {
                    "int": "Integer",
                    "mcq": "MCQ",
                    "med": "MED",
                    "rol": "Roll",
                }
                for k, boxvals in all_c_box_vals.items():
                    axes[ctr].title.set_text(type_name[k] + " Type")
                    axes[ctr].boxplot(boxvals)
                    # thrline=axes[ctr].axhline(per_omr_threshold_avg,color='red',ls='--')
                    # thrline.set_label("Average THR")
                    axes[ctr].set_ylabel("Intensity")
                    axes[ctr].set_xticklabels(q_nums[k])
                    # axes[ctr].legend()
                    ctr += 1
                # imshow will do the waiting
                plt.tight_layout(pad=0.5)
                plt.show()

            if config.outputs.show_image_level >= 3 and final_align is not None:
                final_align = ImageUtils.resize_util_h(
                    final_align, int(config.dimensions.display_height)
                )
                # [final_align.shape[1],0])
                InteractionUtils.show(
                    "Template Alignment Adjustment", final_align, 0, 0, config=config
                )

            if config.outputs.save_detections and save_dir is not None:
                if multi_roll:
                    save_dir = save_dir.joinpath("_MULTI_")
                image_path = str(save_dir.joinpath(name))
                ImageUtils.save_img(image_path, final_marked)

            self.append_save_img(2, final_marked)

            if save_dir is not None:
                for i in range(config.outputs.save_image_level):
                    self.save_image_stacks(i + 1, name, save_dir)

            return omr_response, final_marked, multi_marked, multi_roll

        except Exception as e:
            raise e

    @staticmethod
    def draw_template_layout(img, template, shifted=True, draw_qvals=False, border=-1):
        img = ImageUtils.resize_util(
            img, template.page_dimensions[0], template.page_dimensions[1]
        )
        final_align = img.copy()
        for field_block in template.field_blocks:
            s, d = field_block.origin, field_block.dimensions
            box_w, box_h = field_block.bubble_dimensions
            shift = field_block.shift
            if shifted:
                cv2.rectangle(
                    final_align,
                    (s[0] + shift, s[1]),
                    (s[0] + shift + d[0], s[1] + d[1]),
                    CLR_BLACK,
                    3,
                )
            else:
                cv2.rectangle(
                    final_align,
                    (s[0], s[1]),
                    (s[0] + d[0], s[1] + d[1]),
                    CLR_BLACK,
                    3,
                )
            for field_block_bubbles in field_block.traverse_bubbles:
                for pt in field_block_bubbles:
                    x, y = (pt.x + field_block.shift, pt.y) if shifted else (pt.x, pt.y)
                    cv2.rectangle(
                        final_align,
                        (int(x + box_w / 10), int(y + box_h / 10)),
                        (int(x + box_w - box_w / 10), int(y + box_h - box_h / 10)),
                        CLR_GRAY,
                        border,
                    )
                    if draw_qvals:
                        rect = [y, y + box_h, x, x + box_w]
                        cv2.putText(
                            final_align,
                            f"{int(cv2.mean(img[rect[0] : rect[1], rect[2] : rect[3]])[0])}",
                            (rect[2] + 2, rect[0] + (box_h * 2) // 3),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            CLR_BLACK,
                            2,
                        )
            if shifted:
                text_in_px = cv2.getTextSize(
                    field_block.name, cv2.FONT_HERSHEY_SIMPLEX, TEXT_SIZE, 4
                )
                cv2.putText(
                    final_align,
                    field_block.name,
                    (int(s[0] + d[0] - text_in_px[0][0]), int(s[1] - text_in_px[0][1])),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    TEXT_SIZE,
                    CLR_BLACK,
                    4,
                )
        return final_align

    def get_global_threshold(
        self,
        q_vals_orig,
        plot_title=None,
        plot_show=True,
        sort_in_plot=True,
        looseness=1,
    ):
        """
        Note: Cannot assume qStrip has only-gray or only-white bg
            (in which case there is only one jump).
        So there will be either 1 or 2 jumps.
        1 Jump :
                ......
                ||||||
                ||||||  <-- risky THR
                ||||||  <-- safe THR
            ....||||||
            ||||||||||

        2 Jumps :
                ......
                |||||| <-- wrong THR
            ....||||||
            |||||||||| <-- safe THR
            ..||||||||||
            ||||||||||||

        The abstract "First LARGE GAP" is perfect for this.
        Current code is considering ONLY TOP 2 jumps(>= MIN_GAP) to be big,
            gives the smaller one

        """
        config = self.tuning_config
        PAGE_TYPE_FOR_THRESHOLD, MIN_JUMP, JUMP_DELTA = map(
            config.threshold_params.get,
            [
                "PAGE_TYPE_FOR_THRESHOLD",
                "MIN_JUMP",
                "JUMP_DELTA",
            ],
        )

        global_default_threshold = (
            GLOBAL_PAGE_THRESHOLD_WHITE
            if PAGE_TYPE_FOR_THRESHOLD == "white"
            else GLOBAL_PAGE_THRESHOLD_BLACK
        )

        # Sort the Q bubbleValues
        # TODO: Change var name of q_vals
        q_vals = sorted(q_vals_orig)
        # Find the FIRST LARGE GAP and set it as threshold:
        ls = (looseness + 1) // 2
        l = len(q_vals) - ls
        max1, thr1 = MIN_JUMP, global_default_threshold
        for i in range(ls, l):
            jump = q_vals[i + ls] - q_vals[i - ls]
            if jump > max1:
                max1 = jump
                thr1 = q_vals[i - ls] + jump / 2

        # NOTE: thr2 is deprecated, thus is JUMP_DELTA
        # Make use of the fact that the JUMP_DELTA(Vertical gap ofc) between
        # values at detected jumps would be atleast 20
        max2, thr2 = MIN_JUMP, global_default_threshold
        # Requires atleast 1 gray box to be present (Roll field will ensure this)
        for i in range(ls, l):
            jump = q_vals[i + ls] - q_vals[i - ls]
            new_thr = q_vals[i - ls] + jump / 2
            if jump > max2 and abs(thr1 - new_thr) > JUMP_DELTA:
                max2 = jump
                thr2 = new_thr
        # global_thr = min(thr1,thr2)
        global_thr, j_low, j_high = thr1, thr1 - max1 // 2, thr1 + max1 // 2

        # # For normal images
        # thresholdRead =  116
        # if(thr1 > thr2 and thr2 > thresholdRead):
        #     print("Note: taking safer thr line.")
        #     global_thr, j_low, j_high = thr2, thr2 - max2//2, thr2 + max2//2

        if plot_title:
            _, ax = plt.subplots()
            ax.bar(range(len(q_vals_orig)), q_vals if sort_in_plot else q_vals_orig)
            ax.set_title(plot_title)
            thrline = ax.axhline(global_thr, color="green", ls="--", linewidth=5)
            thrline.set_label("Global Threshold")
            thrline = ax.axhline(thr2, color="red", ls=":", linewidth=3)
            thrline.set_label("THR2 Line")
            # thrline=ax.axhline(j_low,color='red',ls='-.', linewidth=3)
            # thrline=ax.axhline(j_high,color='red',ls='-.', linewidth=3)
            # thrline.set_label("Boundary Line")
            # ax.set_ylabel("Mean Intensity")
            ax.set_ylabel("Values")
            ax.set_xlabel("Position")
            ax.legend()
            if plot_show:
                plt.title(plot_title)
                plt.show()

        return global_thr, j_low, j_high

    def get_local_threshold(
        self, q_vals, global_thr, no_outliers, plot_title=None, plot_show=True
    ):
        """
        TODO: Update this documentation too-
        //No more - Assumption : Colwise background color is uniformly gray or white,
                but not alternating. In this case there is atmost one jump.

        0 Jump :
                        <-- safe THR?
            .......
            ...|||||||
            ||||||||||  <-- safe THR?
        // How to decide given range is above or below gray?
            -> global q_vals shall absolutely help here. Just run same function
                on total q_vals instead of colwise _//
        How to decide it is this case of 0 jumps

        1 Jump :
                ......
                ||||||
                ||||||  <-- risky THR
                ||||||  <-- safe THR
            ....||||||
            ||||||||||

        """
        config = self.tuning_config
        # Sort the Q bubbleValues
        q_vals = sorted(q_vals)

        # Small no of pts cases:
        # base case: 1 or 2 pts
        if len(q_vals) < 3:
            thr1 = (
                global_thr
                if np.max(q_vals) - np.min(q_vals) < config.threshold_params.MIN_GAP
                else np.mean(q_vals)
            )
        else:
            # qmin, qmax, qmean, qstd = round(np.min(q_vals),2), round(np.max(q_vals),2),
            #   round(np.mean(q_vals),2), round(np.std(q_vals),2)
            # GVals = [round(abs(q-qmean),2) for q in q_vals]
            # gmean, gstd = round(np.mean(GVals),2), round(np.std(GVals),2)
            # # DISCRETION: Pretty critical factor in reading response
            # # Doesn't work well for small number of values.
            # DISCRETION = 2.7 # 2.59 was closest hit, 3.0 is too far
            # L2MaxGap = round(max([abs(g-gmean) for g in GVals]),2)
            # if(L2MaxGap > DISCRETION*gstd):
            #     no_outliers = False

            # # ^Stackoverflow method
            # print(field_label, no_outliers,"qstd",round(np.std(q_vals),2), "gstd", gstd,
            #   "Gaps in gvals",sorted([round(abs(g-gmean),2) for g in GVals],reverse=True),
            #   '\t',round(DISCRETION*gstd,2), L2MaxGap)

            # else:
            # Find the LARGEST GAP and set it as threshold: //(FIRST LARGE GAP)
            l = len(q_vals) - 1
            max1, thr1 = config.threshold_params.MIN_JUMP, 255
            for i in range(1, l):
                jump = q_vals[i + 1] - q_vals[i - 1]
                if jump > max1:
                    max1 = jump
                    thr1 = q_vals[i - 1] + jump / 2
            # print(field_label,q_vals,max1)

            confident_jump = (
                config.threshold_params.MIN_JUMP
                + config.threshold_params.CONFIDENT_SURPLUS
            )
            # If not confident, then only take help of global_thr
            if max1 < confident_jump:
                if no_outliers:
                    # All Black or All White case
                    thr1 = global_thr
                else:
                    # TODO: Low confidence parameters here
                    pass

            # if(thr1 == 255):
            #     print("Warning: threshold is unexpectedly 255! (Outlier Delta issue?)",plot_title)

        # Make a common plot function to show local and global thresholds
        if plot_show and plot_title is not None:
            _, ax = plt.subplots()
            ax.bar(range(len(q_vals)), q_vals)
            thrline = ax.axhline(thr1, color="green", ls=("-."), linewidth=3)
            thrline.set_label("Local Threshold")
            thrline = ax.axhline(global_thr, color="red", ls=":", linewidth=5)
            thrline.set_label("Global Threshold")
            ax.set_title(plot_title)
            ax.set_ylabel("Bubble Mean Intensity")
            ax.set_xlabel("Bubble Number(sorted)")
            ax.legend()
            # TODO append QStrip to this plot-
            # appendSaveImg(6,getPlotImg())
            if plot_show:
                plt.show()
        return thr1

    def append_save_img(self, key, img):
        if self.save_image_level >= int(key):
            self.save_img_list[key].append(img.copy())

    def save_image_stacks(self, key, filename, save_dir):
        config = self.tuning_config
        if self.save_image_level >= int(key) and self.save_img_list[key] != []:
            name = os.path.splitext(filename)[0]
            result = np.hstack(
                tuple(
                    [
                        ImageUtils.resize_util_h(img, config.dimensions.display_height)
                        for img in self.save_img_list[key]
                    ]
                )
            )
            result = ImageUtils.resize_util(
                result,
                min(
                    len(self.save_img_list[key]) * config.dimensions.display_width // 3,
                    int(config.dimensions.display_width * 2.5),
                ),
            )
            ImageUtils.save_img(f"{save_dir}stack/{name}_{str(key)}_stack.jpg", result)

    def reset_all_save_img(self):
        for i in range(self.save_image_level):
            self.save_img_list[i + 1] = []
