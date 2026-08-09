from src.constants.common import FIELD_TYPES
from src.schemas.constants import ARRAY_OF_STRINGS, FIELD_STRING_TYPE

positive_number = {"type": "number", "minimum": 0}
positive_integer = {"type": "integer", "minimum": 0}
two_positive_integers = {
    "type": "array",
    "prefixItems": [
        positive_integer,
        positive_integer,
    ],
    "maxItems": 2,
    "minItems": 2,
}
two_positive_numbers = {
    "type": "array",
    "prefixItems": [
        positive_number,
        positive_number,
    ],
    "maxItems": 2,
    "minItems": 2,
}
zero_to_one_number = {
    "type": "number",
    "minimum": 0,
    "maximum": 1,
}

ocr_options_schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "lang": {"type": "string"},
        "det": {"type": "boolean"},
        "rec": {"type": "boolean"},
        "cls": {"type": "boolean"},
        "returnConfidence": {"type": "boolean"},
        "archiveRegion": {"type": "boolean"},
    },
}

field_block_ocrs_schema = {
    "description": "OCR recognition regions parsed with PaddleOCR",
    "type": "object",
    "patternProperties": {
        "^.*$": {
            "type": "object",
            "additionalProperties": False,
            "required": ["origin", "dimensions", "fieldLabels"],
            "properties": {
                "fieldLabels": {"type": "array", "items": FIELD_STRING_TYPE},
                "origin": two_positive_integers,
                "dimensions": two_positive_integers,
                "regionCode": {"type": "string"},
                "regionName": {"type": "string"},
                "type": {"type": "string"},
                "ocr": ocr_options_schema,
            },
        }
    },
}

TEMPLATE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/Udayraj123/OMRChecker/tree/master/src/schemas/template-schema.json",
    "title": "Template Validation Schema",
    "description": "OMRChecker input template schema",
    "type": "object",
    "required": [
        "bubbleDimensions",
        "pageDimensions",
        "preProcessors",
        "fieldBlocks",
    ],
    "additionalProperties": False,
    "properties": {
        "bubbleDimensions": {
            **two_positive_integers,
            "description": "The dimensions of the overlay bubble area: [width, height]",
        },
        "customLabels": {
            "description": "The customLabels contain fields that need to be joined together before generating the results sheet",
            "type": "object",
            "patternProperties": {
                "^.*$": {"type": "array", "items": FIELD_STRING_TYPE}
            },
        },
        "outputColumns": {
            "type": "array",
            "items": FIELD_STRING_TYPE,
            "description": "The ordered list of columns to be contained in the output csv(default order: alphabetical)",
        },
        "archiveRegions": {
            "description": "Additional large archive-only regions for manual review. These do not affect OMR or OCR recognition regions.",
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["regionCode", "regionName", "type", "bbox"],
                "properties": {
                    "regionCode": {"type": "string"},
                    "regionName": {"type": "string"},
                    "type": {"type": "string"},
                    "bbox": {
                        "type": "array",
                        "prefixItems": [
                            positive_integer,
                            positive_integer,
                            positive_integer,
                            positive_integer,
                        ],
                        "maxItems": 4,
                        "minItems": 4,
                    },
                },
            },
        },
        "pageDimensions": {
            **two_positive_integers,
            "description": "The dimensions(width, height) to which the page will be resized to before applying template",
        },
        "preProcessors": {
            "description": "Custom configuration values to use in the template's directory",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": [
                            "CropOnMarkers",
                            "CropPage",
                            "FeatureBasedAlignment",
                            "GaussianBlur",
                            "Levels",
                            "MedianBlur",
                        ],
                    },
                },
                "required": ["name", "options"],
                "allOf": [
                    {
                        "if": {"properties": {"name": {"const": "CropOnMarkers"}}},
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "apply_erode_subtract": {"type": "boolean"},
                                        "marker_rescale_range": two_positive_numbers,
                                        "marker_rescale_steps": {"type": "number"},
                                        "max_matching_variation": {"type": "number"},
                                        "min_matching_threshold": {"type": "number"},
                                        "relativePath": {"type": "string"},
                                        "sheetToMarkerWidthRatio": {"type": "number"},
                                    },
                                    "required": ["relativePath"],
                                }
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {"name": {"const": "FeatureBasedAlignment"}}
                        },
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "2d": {"type": "boolean"},
                                        "goodMatchPercent": {"type": "number"},
                                        "maxFeatures": {"type": "integer"},
                                        "reference": {"type": "string"},
                                    },
                                    "required": ["reference"],
                                }
                            }
                        },
                    },
                    {
                        "if": {"properties": {"name": {"const": "Levels"}}},
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "gamma": zero_to_one_number,
                                        "high": zero_to_one_number,
                                        "low": zero_to_one_number,
                                    },
                                }
                            }
                        },
                    },
                    {
                        "if": {"properties": {"name": {"const": "MedianBlur"}}},
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {"kSize": {"type": "integer"}},
                                }
                            }
                        },
                    },
                    {
                        "if": {"properties": {"name": {"const": "GaussianBlur"}}},
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "kSize": two_positive_integers,
                                        "sigmaX": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    {
                        "if": {"properties": {"name": {"const": "CropPage"}}},
                        "then": {
                            "properties": {
                                "options": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "morphKernel": two_positive_integers
                                    },
                                }
                            }
                        },
                    },
                ],
            },
        },
        "fieldBlocks": {
            "description": "The fieldBlocks denote small groups of adjacent fields",
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "required": ["origin", "fieldLabels"],
                    "properties": {
                        "engine": {
                            "type": "string",
                            "enum": ["omr", "paddleocr"],
                        },
                        "bubbleDimensions": two_positive_numbers,
                        "bubblesGap": positive_number,
                        "bubbleValues": ARRAY_OF_STRINGS,
                        "direction": {
                            "type": "string",
                            "enum": ["horizontal", "vertical"],
                        },
                        "emptyValue": {"type": "string"},
                        "fieldLabels": {"type": "array", "items": FIELD_STRING_TYPE},
                        "labelsGap": positive_number,
                        "multiSelect": {"type": "boolean"},
                        "origin": two_positive_integers,
                        "dimensions": two_positive_integers,
                        "regionCode": {"type": "string"},
                        "regionName": {"type": "string"},
                        "type": {"type": "string"},
                        "fieldType": {
                            "type": "string",
                            "enum": list(FIELD_TYPES.keys()),
                        },
                        "ocr": ocr_options_schema,
                    },
                    "allOf": [
                        {
                            "if": {
                                "required": ["engine"],
                                "properties": {"engine": {"const": "paddleocr"}},
                            },
                            "then": {"required": ["dimensions"]},
                            "else": {
                                "required": ["bubblesGap", "labelsGap"],
                                "oneOf": [
                                    {"required": ["fieldType"]},
                                    {"required": ["bubbleValues", "direction"]},
                                ],
                            },
                        }
                    ],
                }
            },
        },
        "fieldBlockOcrs": field_block_ocrs_schema,
        "emptyValue": {
            "description": "The value to be used in case of empty bubble detected at global level.",
            "type": "string",
        },
    },
}
