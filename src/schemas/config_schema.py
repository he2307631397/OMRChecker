CONFIG_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/Udayraj123/OMRChecker/tree/master/src/schemas/config-schema.json",
    "title": "Config Schema",
    "description": "OMRChecker config schema for custom tuning",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "dimensions": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "display_height": {"type": "integer"},
                "display_width": {"type": "integer"},
                "processing_height": {"type": "integer"},
                "processing_width": {"type": "integer"},
            },
        },
        "threshold_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "GAMMA_LOW": {"type": "number", "minimum": 0, "maximum": 1},
                "MIN_GAP": {"type": "integer", "minimum": 10, "maximum": 100},
                "MIN_JUMP": {"type": "integer", "minimum": 10, "maximum": 100},
                "CONFIDENT_SURPLUS": {"type": "integer", "minimum": 0, "maximum": 20},
                "JUMP_DELTA": {"type": "integer", "minimum": 10, "maximum": 100},
                "PAGE_TYPE_FOR_THRESHOLD": {
                    "enum": ["white", "black"],
                    "type": "string",
                },
            },
        },
        "alignment_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "auto_align": {"type": "boolean"},
                "match_col": {"type": "integer", "minimum": 0, "maximum": 10},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 100},
                "stride": {"type": "integer", "minimum": 1, "maximum": 10},
                "thickness": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
        "pdf_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "pdf_dpi": {
                    "anyOf": [
                        {"type": "integer", "minimum": 72, "maximum": 600},
                        {"type": "string", "enum": ["auto"]},
                    ],
                },
                "pdf_page": {
                    "anyOf": [
                        {"type": "integer", "minimum": 1},
                        {"type": "null"},
                        {"type": "string", "pattern": r"^\d+(?:-\d*)?$"},
                        {
                            "type": "array",
                            "items": {
                                "anyOf": [
                                    {"type": "integer", "minimum": 1},
                                    {"type": "string", "pattern": r"^\d+(?:-\d*)?$"},
                                ]
                            },
                            "minItems": 1,
                        },
                    ],
                },
            },
        },
        "weak_mark_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "min_gap": {"type": "number", "minimum": 0, "maximum": 100},
                "min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "adaptive_min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "min_delta_from_page_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "min_page_z_score": {"type": "number", "minimum": 0, "maximum": 20},
                "min_dark_pixel_ratio": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "min_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_use_density": {"type": "boolean"},
                "conflict_min_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_min_center_density": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "detect_true_multi_conflicts": {"type": "boolean"},
                "true_multi_min_center_density": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "true_multi_max_top_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "resolve_single_choice_conflicts": {"type": "boolean"},
                "conflict_min_gap": {"type": "number", "minimum": 0, "maximum": 100},
                "conflict_min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "conflict_auto_resolve_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_review_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "weak_fill_auto_resolve_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "weak_fill_review_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "max_mean": {"type": "number", "minimum": 0, "maximum": 255},
                "supported_field_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "exclude_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "weak_identifier_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "exclude_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "resolve_conflicts": {"type": "boolean"},
                "conflict_auto_resolve_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_review_min_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "min_gap": {"type": "number", "minimum": 0, "maximum": 100},
                "min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "adaptive_min_gap": {"type": "number", "minimum": 0, "maximum": 100},
                "adaptive_min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "min_page_z_score": {"type": "number", "minimum": 0, "maximum": 20},
                "min_dark_pixel_ratio": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "min_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_use_density": {"type": "boolean"},
                "conflict_min_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "conflict_min_center_density": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "max_mean": {"type": "number", "minimum": 0, "maximum": 255},
                "adaptive_max_mean": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 255,
                },
                "supported_field_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
        },
        "weak_multi_mark_params": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "only_when_blank": {"type": "boolean"},
                "min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "max_mean": {"type": "number", "minimum": 0, "maximum": 255},
                "max_marks": {"type": "integer", "minimum": 1, "maximum": 10},
                "filter_use_density": {"type": "boolean"},
                "filter_min_center_density": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "filter_min_density_gap": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "full_select_min_center_density": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "full_select_max_density_spread": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "full_select_fallback_enabled": {"type": "boolean"},
                "full_select_max_mean": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 255,
                },
                "full_select_min_delta_from_blank": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
                "full_select_max_spread": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
        },
        "outputs": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "show_image_level": {"type": "integer", "minimum": 0, "maximum": 6},
                "save_image_level": {"type": "integer", "minimum": 0, "maximum": 6},
                "save_detections": {"type": "boolean"},
                # This option moves multimarked files into a separate folder for manual checking, skipping evaluation
                "filter_out_multimarked_files": {"type": "boolean"},
            },
        },
    },
}
