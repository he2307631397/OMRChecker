import csv
from pathlib import Path

from scripts.run_omr_regression import summarize_csv, summarize_log


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_id",
        "input_path",
        "output_path",
        "score",
        "id1",
        "id2",
        "q1",
        "q2",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_summarize_csv_counts_id_answer_blanks_and_blank_rows(tmp_path):
    write_csv(
        tmp_path / "Results" / "Results_01.csv",
        [
            {
                "file_id": "a.png",
                "input_path": "a.pdf",
                "output_path": "a_checked.png",
                "score": "0",
                "id1": "1",
                "id2": "",
                "q1": "A",
                "q2": "",
            },
            {
                "file_id": "b.png",
                "input_path": "b.pdf",
                "output_path": "b_checked.png",
                "score": "0",
                "id1": "2",
                "id2": "3",
                "q1": "B",
                "q2": "C",
            },
        ],
    )

    summary = summarize_csv(tmp_path)

    assert summary["rows"] == 2
    assert summary["id_blank_cells"] == 1
    assert summary["q_blank_cells"] == 1
    assert summary["blank_cells"] == 2
    assert summary["blank_rows"] == 1
    assert summary["blanks"] == [("a.png", "id2"), ("a.png", "q2")]


def test_summarize_log_counts_fallback_and_review_events(tmp_path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "Weak identifier fallback\n"
        "Weak mark fallback\n"
        "Weak mark fallback\n"
        "Weak multi-mark fallback\n"
        "Weak multi full-select fallback\n"
        "Weak mark candidate review\n"
        "Single-choice conflict\n",
        encoding="utf-8",
    )

    summary = summarize_log(log_path)

    assert summary["Weak identifier fallback"] == 1
    assert summary["Weak mark fallback"] == 2
    assert summary["Weak multi-mark fallback"] == 1
    assert summary["Weak multi full-select fallback"] == 1
    assert summary["Weak mark candidate review"] == 1
    assert summary["Single-choice conflict"] == 1
