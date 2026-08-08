import argparse
import csv
import json
import os
from csv import QUOTE_NONNUMERIC
from pathlib import Path
from time import localtime, strftime

import pandas as pd

from src.logger import logger


OCR_RESULTS_COLUMNS = [
    "file_id",
    "input_path",
    "output_path",
    "field",
    "value",
    "confidence",
    "engine",
    "regionCode",
    "regionName",
    "type",
    "bbox",
    "artifactLocalPath",
]


def load_json(path, **rest):
    try:
        with open(path, "r") as f:
            loaded = json.load(f, **rest)
    except json.decoder.JSONDecodeError as error:
        logger.critical(f"Error when loading json file at: '{path}'\n{error}")
        exit(1)
    return loaded


def append_ocr_results_csv(results_dir, rows):
    if not rows:
        return None

    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "OcrResults.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OCR_RESULTS_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            serialized = {column: row.get(column, "") for column in OCR_RESULTS_COLUMNS}
            bbox = serialized.get("bbox")
            if isinstance(bbox, (dict, list)):
                serialized["bbox"] = json.dumps(bbox, ensure_ascii=False, sort_keys=True)
            writer.writerow(serialized)
    return csv_path


class Paths:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.save_marked_dir = output_dir.joinpath("CheckedOMRs")
        self.results_dir = output_dir.joinpath("Results")
        self.manual_dir = output_dir.joinpath("Manual")
        self.evaluation_dir = output_dir.joinpath("Evaluation")
        self.errors_dir = self.manual_dir.joinpath("ErrorFiles")
        self.multi_marked_dir = self.manual_dir.joinpath("MultiMarkedFiles")


def setup_dirs_for_paths(paths):
    logger.info("Checking Directories...")
    for save_output_dir in [paths.save_marked_dir]:
        if not os.path.exists(save_output_dir):
            logger.info(f"Created : {save_output_dir}")
            os.makedirs(save_output_dir)
            os.mkdir(save_output_dir.joinpath("stack"))
            os.mkdir(save_output_dir.joinpath("_MULTI_"))
            os.mkdir(save_output_dir.joinpath("_MULTI_", "stack"))

    for save_output_dir in [paths.manual_dir, paths.results_dir, paths.evaluation_dir]:
        if not os.path.exists(save_output_dir):
            logger.info(f"Created : {save_output_dir}")
            os.makedirs(save_output_dir)

    for save_output_dir in [paths.multi_marked_dir, paths.errors_dir]:
        if not os.path.exists(save_output_dir):
            logger.info(f"Created : {save_output_dir}")
            os.makedirs(save_output_dir)


def setup_outputs_for_template(paths, template):
    # TODO: consider moving this into a class instance
    ns = argparse.Namespace()
    logger.info("Checking Files...")

    # Include current output paths
    ns.paths = paths

    ns.empty_resp = [""] * len(template.output_columns)
    ns.sheetCols = [
        "file_id",
        "input_path",
        "output_path",
        "score",
    ] + template.output_columns
    ns.weakFillReviewCols = [
        "file_id",
        "input_path",
        "output_path",
        "review_type",
        "field",
        "original_value",
        "candidate",
        "confidence",
        "status",
        "reason",
        "evidence",
        "score",
        "legacy_rejection",
        "ambiguity",
        "density_gap",
        "center_density",
        "center_edge_ratio",
        "threshold_vote_ratio",
        "multiscale_stability",
    ]
    ns.OUTPUT_SET = []
    ns.files_obj = {}
    TIME_NOW_HRS = strftime("%I%p", localtime())
    ns.filesMap = {
        "Results": os.path.join(paths.results_dir, f"Results_{TIME_NOW_HRS}.csv"),
        "WeakFillReview": os.path.join(paths.results_dir, "WeakFillReview.csv"),
        "MultiMarked": os.path.join(paths.manual_dir, "MultiMarkedFiles.csv"),
        "Errors": os.path.join(paths.manual_dir, "ErrorFiles.csv"),
    }

    for file_key, file_name in ns.filesMap.items():
        if not os.path.exists(file_name):
            logger.info(f"Created new file: '{file_name}'")
            # moved handling of files to pandas csv writer
            ns.files_obj[file_key] = file_name
            # Create Header Columns
            sheet_cols = (
                ns.weakFillReviewCols
                if file_key == "WeakFillReview"
                else ns.sheetCols
            )
            pd.DataFrame([sheet_cols], dtype=str).to_csv(
                ns.files_obj[file_key],
                mode="a",
                quoting=QUOTE_NONNUMERIC,
                header=False,
                index=False,
            )
        else:
            logger.info(f"Present : appending to '{file_name}'")
            ns.files_obj[file_key] = open(file_name, "a")

    return ns
