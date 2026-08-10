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
            "engine": "omr",
            "regionCode": "candidateNumber",
            "regionName": "准考证号区域",
            "type": "DIGIT",
            "items": [
                {"field": "id1", "value": "3", "confidence": 1.0},
                {"field": "id2", "value": "5", "confidence": 1.0},
            ],
        },
        {
            "engine": "omr",
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
        region for region in rows[0]["answers"] if region["regionCode"] == "fillBank"
    )
    assert blank_region["engine"] == "ocr"
    assert blank_region["items"] == [
        {
            "field": "score",
            "value": "5",
            "confidence": 0.982,
            "artifactLocalPath": "artifacts/sheet-1/blankScore1.png",
        }
    ]
    assert "engine" not in blank_region["items"][0]


def test_read_results_csv_groups_fill_blank_and_solution_by_business_contract(tmp_path):
    results_dir = tmp_path / "output" / "Results"
    results_dir.mkdir(parents=True)
    results_csv = results_dir / "Results_001.csv"
    results_csv.write_text(
        "file_id,input_path,output_path,score,fill_blank_score_text,fill_q12_answer_text,fill_q13_answer_text,q14_score_text,solution_q14_answer_text\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,0,15,,,19,过程文本\n",
        encoding="utf-8",
    )
    (results_dir / "OcrResults.csv").write_text(
        "file_id,input_path,output_path,field,value,confidence,engine,regionCode,regionName,type,bbox,artifactLocalPath\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,fill_blank_score_text,15,0.99,paddleocr,FillBlank,填空题,score,,\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,fill_q12_answer_text,,0,paddleocr,Q12,第12题填空题,answer,,\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,fill_q13_answer_text,,0,paddleocr,Q13,第13题填空题,answer,,\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,q14_score_text,19,0.97,paddleocr,Q14,第14题解答题,score,,\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,solution_q14_answer_text,过程文本,0.88,paddleocr,Q14,第14题解答题,answer,,\n",
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
          "fieldBlocks": {},
          "fieldBlockOcrs": {
            "FillBlankScoreOcr": {"fieldLabels": ["fill_blank_score_text"], "origin": [0, 0], "dimensions": [10, 10], "regionCode": "FillBlank", "regionName": "填空题", "type": "score"},
            "FillQ12AnswerOcr": {"fieldLabels": ["fill_q12_answer_text"], "origin": [0, 0], "dimensions": [10, 10], "regionCode": "Q12", "regionName": "第12题填空题", "type": "answer"},
            "FillQ13AnswerOcr": {"fieldLabels": ["fill_q13_answer_text"], "origin": [0, 0], "dimensions": [10, 10], "regionCode": "Q13", "regionName": "第13题填空题", "type": "answer"},
            "Q14ScoreOcr": {"fieldLabels": ["q14_score_text"], "origin": [0, 0], "dimensions": [10, 10], "regionCode": "Q14", "regionName": "第14题解答题", "type": "score"},
            "Q14AnswerOcr": {"fieldLabels": ["solution_q14_answer_text"], "origin": [0, 0], "dimensions": [10, 10], "regionCode": "Q14", "regionName": "第14题解答题", "type": "answer"}
          },
          "outputColumns": ["fill_blank_score_text", "fill_q12_answer_text", "fill_q13_answer_text", "q14_score_text", "solution_q14_answer_text"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    row = omr_service.read_results_csv(results_csv, template_dir=template_dir)[0]

    fill_region = next(region for region in row["answers"] if region["regionCode"] == "fillBank")
    solution_region = next(region for region in row["answers"] if region["regionCode"] == "solution")
    assert fill_region == {
        "regionCode": "fillBank",
        "regionName": "填空题",
        "type": "FILL_BLANK",
        "engine": "ocr",
        "items": [
            {"field": "score", "value": "15", "confidence": 0.99},
            {"field": "q12", "value": "", "confidence": 0.0},
            {"field": "q13", "value": "", "confidence": 0.0},
        ],
    }
    assert solution_region == {
        "regionCode": "solution",
        "regionName": "解答题",
        "type": "SOLUTION",
        "engine": "ocr",
        "items": [
            {"field": "score", "value": "19", "confidence": 0.97},
            {"field": "q14", "value": "过程文本", "confidence": 0.88},
        ],
    }
