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
        "file_id,input_path,output_path,score,id1,id2,q1,q2\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,2,3,5,A,\n",
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
            },
            "student_id_area": {
              "fieldType": "QTYPE_INT",
              "fieldLabels": ["id1..2"],
              "origin": [0, 20],
              "bubblesGap": 10,
              "labelsGap": 10
            }
          },
          "outputColumns": ["id1..2", "q1..2"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    rows = omr_service.read_results_csv(results_csv, template_dir=template_dir)

    assert rows[0]["answers_flat"] == {"q1": "A", "q2": ""}
    assert rows[0]["answers"] == [
        {
            "regionCode": "candidateNumber",
            "regionName": "准考证号区域",
            "type": "DIGIT",
            "items": [
                {"field": "id1", "value": "3", "confidence": 1.0},
                {"field": "id2", "value": "5", "confidence": 1.0},
            ],
        },
        {
            "regionCode": "singleChoice",
            "regionName": "单选题区域",
            "type": "SINGLE_CHOICE",
            "items": [
                {"field": "q1", "value": "A", "confidence": 0.876},
                {"field": "q2", "value": "", "confidence": 0.0},
            ],
        },
    ]


def test_read_results_csv_includes_template_paddleocr_fields_with_confidence(tmp_path):
    results_dir = tmp_path / "output" / "Results"
    results_dir.mkdir(parents=True)
    results_csv = results_dir / "Results_001.csv"
    results_csv.write_text(
        "file_id,input_path,output_path,score,id1,q1,blankScore1,solutionAnswer2\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,2,3,A,5,过程文本\n",
        encoding="utf-8",
    )
    (results_dir / "OcrResults.csv").write_text(
        "file_id,input_path,output_path,field,value,confidence,engine,regionCode,regionName,type,bbox,artifactLocalPath\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,blankScore1,5,0.982,paddleocr,blankScore,填空题得分区域,BLANK_SCORE,\"{\"\"height\"\": 60, \"\"width\"\": 160, \"\"x\"\": 120, \"\"y\"\": 80}\",artifacts/sheet-1/blankScore1.png\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,solutionAnswer2,过程文本,0.876,paddleocr,solutionAnswer,解答题解答区域,SOLUTION_ANSWER,\"{\"\"height\"\": 220, \"\"width\"\": 500, \"\"x\"\": 100, \"\"y\"\": 200}\",artifacts/sheet-1/solutionAnswer2.png\n",
        encoding="utf-8",
    )
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "template.json").write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [10, 10],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {
            "student_id_area": {"fieldType": "QTYPE_INT", "fieldLabels": ["id1"], "origin": [0, 20], "bubblesGap": 10, "labelsGap": 10},
            "choice_area_1": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q1"], "origin": [0, 0], "bubblesGap": 10, "labelsGap": 10}
          },
          "fieldBlockOcrs": {
            "blank_score_1": {"fieldLabels": ["blankScore1"], "origin": [120, 80], "dimensions": [160, 60], "regionCode": "blankScore", "regionName": "填空题得分区域", "type": "BLANK_SCORE", "ocr": {"archiveRegion": true}},
            "solution_answer_2": {"fieldLabels": ["solutionAnswer2"], "origin": [100, 200], "dimensions": [500, 220], "regionCode": "solutionAnswer", "regionName": "解答题解答区域", "type": "SOLUTION_ANSWER", "ocr": {"archiveRegion": true}}
          },
          "outputColumns": ["id1", "q1", "blankScore1", "solutionAnswer2"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    rows = omr_service.read_results_csv(results_csv, template_dir=template_dir)

    assert rows[0]["answers_flat"] == {
        "q1": "A",
        "blankScore1": "5",
        "solutionAnswer2": "过程文本",
    }
    blank_region = next(
        region for region in rows[0]["answers"] if region["regionCode"] == "blankScore"
    )
    assert blank_region["engine"] == "paddleocr"
    assert blank_region["items"] == [
        {
            "field": "blankScore1",
            "value": "5",
            "confidence": 0.982,
            "artifactLocalPath": "artifacts/sheet-1/blankScore1.png",
        }
    ]
    assert "engine" not in blank_region["items"][0]
