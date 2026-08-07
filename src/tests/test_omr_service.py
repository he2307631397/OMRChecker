from pathlib import Path

from src.services import omr_service


def test_run_omr_directory_preserves_output_directory(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    def fake_entry_point(root_dir, args):
        results_dir = Path(args["output_dir"]) / "Results"
        checked_dir = Path(args["output_dir"]) / "CheckedOMRs"
        results_dir.mkdir(parents=True)
        checked_dir.mkdir(parents=True)
        (results_dir / "Results_001.csv").write_text(
            "file_id,input_path,output_path,score\n"
            "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,1\n",
            encoding="utf-8",
        )
        (checked_dir / "sheet-1.png").write_bytes(b"checked")

    monkeypatch.setattr(omr_service, "entry_point", fake_entry_point)

    result = omr_service.run_omr_directory(input_dir, output_dir)

    assert len(result.rows) == 1
    assert (output_dir / "Results" / "Results_001.csv").exists()
    assert (output_dir / "CheckedOMRs" / "sheet-1.png").exists()


def test_read_results_csv_groups_answers_by_business_region_with_confidence(tmp_path):
    results_dir = tmp_path / "output" / "Results"
    results_dir.mkdir(parents=True)
    results_csv = results_dir / "Results_001.csv"
    results_csv.write_text(
        "file_id,input_path,output_path,score,q1,q2\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,2,A,\n",
        encoding="utf-8",
    )
    (results_dir / "WeakFillReview.csv").write_text(
        "file_id,input_path,output_path,review_type,field,original_value,candidate,confidence,status,reason,evidence,score,legacy_rejection,ambiguity,density_gap,center_density,center_edge_ratio,threshold_vote_ratio,multiscale_stability\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,weak_fill,q1,,A,0.876,review,,{},0,,,,,,\n",
        encoding="utf-8",
    )
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "template.json").write_text(
        """
        {
          "pageDimensions": [100, 100],
          "bubbleDimensions": [10, 10],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {
            "choice_area_1": {
              "fieldType": "QTYPE_MCQ4",
              "fieldLabels": ["q1..2"],
              "origin": [0, 0],
              "bubblesGap": 10,
              "labelsGap": 10
            }
          },
          "outputColumns": ["q1..2"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    rows = omr_service.read_results_csv(results_csv, template_dir=template_dir)

    assert rows[0]["answers_flat"] == {"q1": "A", "q2": ""}
    assert rows[0]["answers"] == {
        "singleChoice": {
            "regionCode": "singleChoice",
            "regionName": "单选题区域",
            "items": [
                {"field": "q1", "value": "A", "confidence": 0.876},
                {"field": "q2", "value": "", "confidence": 0.0},
            ],
        }
    }
