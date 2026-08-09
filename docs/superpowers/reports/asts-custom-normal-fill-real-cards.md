# ASTS custom normal-fill real-card recognition report

## Scope

This report validates the migrated ASTS template with top-level `fieldBlockOcrs` against the user's real answer-card archive.

- Branch: `paddlocr-integration`
- Input archive: `/Volumes/wdata/work/tech/OMRChecker/docs/assets/自制模板1/正常填涂测试答题卡归档`
- Matching config/template source: `/Volumes/wdata/work/tech/OMRChecker/config/ASTS-HTTP-001/v1`
- Isolated run input: `.jcode_runs/custom-normal-fill-asts`
- Output directory: `outputs/custom-normal-fill-asts`
- Full run log: `/tmp/custom-normal-fill-asts-omr312.log`

## Environment note

The existing `.venv` uses Python 3.14, and `paddlepaddle==3.2.0` has no Python 3.14 wheel. A dedicated Python 3.12 environment was created for this real OCR run:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv-paddle312
.venv-paddle312/bin/python -m pip install -r requirements.txt
.venv-paddle312/bin/python -m pip install paddlepaddle==3.2.0 paddleocr==3.7.0
```

Verification:

```text
Python 3.12.12
paddle 3.2.0
paddleocr 3.7.0
```

## Reproduction command

```bash
rm -rf outputs/custom-normal-fill-asts
script -q /tmp/custom-normal-fill-asts-omr312.log \
  .venv-paddle312/bin/python main.py \
  -i .jcode_runs/custom-normal-fill-asts \
  -o outputs/custom-normal-fill-asts
```

The isolated input directory contained:

- 56 PDF answer cards
- `config.json`
- `template.json`
- `reference.png`

## Run result

The command completed successfully.

```text
exit_code=0
Total file(s) moved        : 0
Total file(s) not moved    : 56
Total file(s) processed    : 56 (Sum Tallied!)
Finished Checking 56 file(s) in 70.4 seconds i.e. ~1.2 minute(s).
OMR Processing Rate        : ~1.26 seconds/OMR
OMR Processing Speed       : ~47.74 OMRs/minute
```

Generated artifacts:

| Artifact | Path | Count |
| --- | --- | ---: |
| Checked OMR images | `outputs/custom-normal-fill-asts/CheckedOMRs/*.png` | 56 |
| Main result CSV | `outputs/custom-normal-fill-asts/Results/Results_12PM.csv` | 56 data rows, 57 lines including header |
| OCR detail CSV | `outputs/custom-normal-fill-asts/Results/OcrResults.csv` | 336 data rows, 337 lines including header |
| Weak fill review CSV | `outputs/custom-normal-fill-asts/Results/WeakFillReview.csv` | 4 data rows, 5 lines including header |
| Manual error CSV | `outputs/custom-normal-fill-asts/Manual/ErrorFiles.csv` | header only |
| Manual multimark CSV | `outputs/custom-normal-fill-asts/Manual/MultiMarkedFiles.csv` | header only |

## CSV summary

Main result CSV:

```text
result_csv=outputs/custom-normal-fill-asts/Results/Results_12PM.csv
result_rows=56
result_columns=29
recognized_fields=1144 of 1400
blank_cells=256
```

The blank cells are concentrated in OCR free-text fields that are blank on these normal-fill cards, plus some score OCR cells:

```text
blank_by_field={
  'fill_q12_answer_text': 56,
  'fill_q13_answer_text': 56,
  'fill_q14_answer_text': 56,
  'solution_q14_answer_text': 56,
  'fill_blank_score_text': 16,
  'q14_score_text': 16
}
```

OCR detail CSV:

```text
ocr_rows=336
ocr_fields={
  'fill_blank_score_text': 56,
  'fill_q12_answer_text': 56,
  'fill_q13_answer_text': 56,
  'fill_q14_answer_text': 56,
  'q14_score_text': 56,
  'solution_q14_answer_text': 56
}
ocr_blank_values=256
```

This confirms that all six `fieldBlockOcrs` fields were executed for all 56 cards, producing `6 * 56 = 336` OCR detail rows.

## Review items

`WeakFillReview.csv` contains four rows:

| file_id | review_type | field | original_value | candidate | confidence | status | reason |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `MX-M3658N_20260731_160125_005.png` | `ID_REVIEW` | `id8` | empty | `6` | 0.902 | `RESOLVED_CANDIDATE` | `weak_identifier_candidate` |
| `MX-M3658N_20260731_160125_016.png` | `SINGLE_CHOICE_CONFLICT_REVIEW` | `q4` | `CD` | `D` | 0.467 | `REVIEW` | `single_choice_conflict` |
| `MX-M3658N_20260731_160125_021.png` | `SINGLE_CHOICE_CONFLICT_REVIEW` | `q2` | `AC` | `C` | 0.457 | `REVIEW` | `single_choice_conflict` |
| `MX-M3658N_20260731_160125_026.png` | `SINGLE_CHOICE_CONFLICT_REVIEW` | `q1` | `AC` | `A` | 0.454 | `REVIEW` | `single_choice_conflict` |

Manual error and multimark CSVs are header-only, so the run did not move any card into manual error directories.

## First-row sanity sample

```json
{
  "file_id": "MX-M3658N_20260731_160125_001.png",
  "input_path": ".jcode_runs/custom-normal-fill-asts/MX-M3658N_20260731_160125_001.pdf",
  "output_path": "outputs/custom-normal-fill-asts/CheckedOMRs/MX-M3658N_20260731_160125_001.png",
  "score": "0",
  "id1": "2",
  "id2": "7",
  "id3": "4",
  "id4": "2",
  "id5": "3",
  "id6": "5",
  "id7": "6",
  "id8": "4",
  "q1": "A",
  "q2": "B",
  "q3": "C",
  "q4": "A",
  "q5": "B",
  "q6": "C",
  "q7": "B",
  "q8": "D",
  "q9": "AC",
  "q10": "BD",
  "q11": "AB",
  "fill_blank_score_text": "15",
  "fill_q12_answer_text": "",
  "fill_q13_answer_text": "",
  "fill_q14_answer_text": "",
  "q14_score_text": "19",
  "solution_q14_answer_text": ""
}
```

## Conclusion

The ASTS template/config in `config/ASTS-HTTP-001/v1` successfully processes the user's 56 normal-fill real PDF answer cards with the migrated `fieldBlockOcrs` structure.

Evidence for `fieldBlockOcrs` functionality:

1. The run exits with code 0.
2. All 56 PDFs are processed.
3. The main result CSV has 56 data rows.
4. `OcrResults.csv` has exactly 336 OCR rows, matching six OCR fields across 56 cards.
5. No card is moved to manual error or multimark directories.

The only review-worthy output is four weak-fill review records, three of which are single-choice conflicts requiring manual judgement. These are recognition-quality review items, not template parsing or `fieldBlockOcrs` migration failures.
