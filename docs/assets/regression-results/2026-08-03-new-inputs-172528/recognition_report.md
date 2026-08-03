# New Inputs 20260803 172528 Local Recognition Report

- Batch: `new-inputs-20260803-172528`
- Run mode: local `python main.py`, non-web
- Input directory: `inputs`
- Output directory: `outputs\new-inputs-20260803-172528`
- Template archive: `docs\assets\templates\new-inputs-20260803-172528`
- Result archive: `docs\assets\regression-results\2026-08-03-new-inputs-172528`

## Summary

| Metric | Value |
| --- | ---: |
| PDF count | 20 |
| Rows processed | 20 |
| Total cells | 380 |
| Nonblank cells | 291 |
| Blank cells | 89 |
| Invalid-format cells | 205 |
| Nonblank recognition rate | 76.58% |
| Valid-format recognition rate | 22.63% |
| Review records | 180 |

## Interpretation

The archived four-scenario template was restored into `inputs` for this batch. Recognition ran successfully, but many ID and single-choice fields contain multi-character values, so the template or mark assumptions likely do not fully match this new batch. The report therefore records both nonblank recognition rate and valid-format recognition rate.

## Review summary

- Status counts: `LEGACY=51, LOW_CONFIDENCE=25, RESOLVED_CANDIDATE=7, REVIEW=97`
- Type counts: `ID_REVIEW=32, SINGLE_CHOICE_CONFLICT_REVIEW=97, WEAK_MARK_REVIEW=51`

## Archived files

- Results: `docs\assets\regression-results\2026-08-03-new-inputs-172528\Results\new_inputs_20260803_172528_Results.csv`
- Review: `docs\assets\regression-results\2026-08-03-new-inputs-172528\Results\new_inputs_20260803_172528_WeakFillReview.csv`
- Invalid cells: `docs\assets\regression-results\2026-08-03-new-inputs-172528\Results\new_inputs_20260803_172528_InvalidCells.csv`
- Blank cells: `docs\assets\regression-results\2026-08-03-new-inputs-172528\Results\new_inputs_20260803_172528_BlankCells.csv`
- Run log: `docs\assets\regression-results\2026-08-03-new-inputs-172528\Results\new_inputs_20260803_172528.log`

## First invalid-format cells

| file_id | field | value | reason |
| --- | --- | --- | --- |
| `MX-M3658N_20260803_172528_001.png` | id1 | `012345678` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id2 | `012345679` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id3 | `01234569` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id4 | `012345689` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id5 | `012345789` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id6 | `012346789` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id7 | `012346789` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | id8 | `012356789` | ID should be one digit |
| `MX-M3658N_20260803_172528_001.png` | q1 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q2 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q3 | `BCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q4 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q5 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q6 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q7 | `AD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_001.png` | q8 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_002.png` | id2 | `01` | ID should be one digit |
| `MX-M3658N_20260803_172528_002.png` | id4 | `08` | ID should be one digit |
| `MX-M3658N_20260803_172528_002.png` | id7 | `012345678` | ID should be one digit |
| `MX-M3658N_20260803_172528_002.png` | id8 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_002.png` | q7 | `CD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_003.png` | id7 | `4567` | ID should be one digit |
| `MX-M3658N_20260803_172528_003.png` | q4 | `CD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | id1 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id2 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id3 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id4 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id5 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id6 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id7 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | id8 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_004.png` | q1 | `ABC` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q2 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q3 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q4 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q5 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q6 | `ABD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q7 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_004.png` | q8 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | id1 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_005.png` | id2 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_005.png` | id3 | `23456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_005.png` | q1 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q2 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q3 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q4 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q6 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q7 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_005.png` | q8 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_006.png` | id2 | `789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id3 | `6789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id4 | `456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id5 | `3456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id6 | `23456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id7 | `123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | id8 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_006.png` | q3 | `CD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_006.png` | q4 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_006.png` | q5 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_006.png` | q8 | `BCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_007.png` | id1 | `67` | ID should be one digit |
| `MX-M3658N_20260803_172528_007.png` | id2 | `23` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id1 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id2 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id3 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id4 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id5 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id6 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id7 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | id8 | `0123456789` | ID should be one digit |
| `MX-M3658N_20260803_172528_008.png` | q1 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q2 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q3 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q4 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q5 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q6 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q7 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_008.png` | q8 | `ABCD` | single-choice should be one option A-D |
| `MX-M3658N_20260803_172528_009.png` | id6 | `01` | ID should be one digit |
| `MX-M3658N_20260803_172528_009.png` | id7 | `012345` | ID should be one digit |
| ... | ... | ... | 125 more rows in InvalidCells.csv |

## Blank cells

| file_id | field |
| --- | --- |
| `MX-M3658N_20260803_172528_002.png` | id5 |
| `MX-M3658N_20260803_172528_002.png` | id6 |
| `MX-M3658N_20260803_172528_002.png` | q1 |
| `MX-M3658N_20260803_172528_002.png` | q3 |
| `MX-M3658N_20260803_172528_002.png` | q4 |
| `MX-M3658N_20260803_172528_002.png` | q6 |
| `MX-M3658N_20260803_172528_002.png` | q8 |
| `MX-M3658N_20260803_172528_002.png` | q9 |
| `MX-M3658N_20260803_172528_002.png` | q10 |
| `MX-M3658N_20260803_172528_002.png` | q11 |
| `MX-M3658N_20260803_172528_003.png` | id1 |
| `MX-M3658N_20260803_172528_003.png` | id3 |
| `MX-M3658N_20260803_172528_003.png` | id4 |
| `MX-M3658N_20260803_172528_003.png` | id5 |
| `MX-M3658N_20260803_172528_003.png` | q1 |
| `MX-M3658N_20260803_172528_003.png` | q2 |
| `MX-M3658N_20260803_172528_003.png` | q3 |
| `MX-M3658N_20260803_172528_003.png` | q5 |
| `MX-M3658N_20260803_172528_003.png` | q6 |
| `MX-M3658N_20260803_172528_003.png` | q8 |
| `MX-M3658N_20260803_172528_003.png` | q9 |
| `MX-M3658N_20260803_172528_005.png` | id5 |
| `MX-M3658N_20260803_172528_005.png` | id6 |
| `MX-M3658N_20260803_172528_005.png` | id7 |
| `MX-M3658N_20260803_172528_005.png` | id8 |
| `MX-M3658N_20260803_172528_006.png` | q1 |
| `MX-M3658N_20260803_172528_006.png` | q6 |
| `MX-M3658N_20260803_172528_006.png` | q7 |
| `MX-M3658N_20260803_172528_006.png` | q9 |
| `MX-M3658N_20260803_172528_007.png` | id5 |
| `MX-M3658N_20260803_172528_007.png` | id6 |
| `MX-M3658N_20260803_172528_007.png` | id7 |
| `MX-M3658N_20260803_172528_007.png` | q1 |
| `MX-M3658N_20260803_172528_007.png` | q2 |
| `MX-M3658N_20260803_172528_007.png` | q3 |
| `MX-M3658N_20260803_172528_007.png` | q5 |
| `MX-M3658N_20260803_172528_007.png` | q6 |
| `MX-M3658N_20260803_172528_007.png` | q7 |
| `MX-M3658N_20260803_172528_009.png` | id2 |
| `MX-M3658N_20260803_172528_009.png` | id3 |
| `MX-M3658N_20260803_172528_009.png` | id4 |
| `MX-M3658N_20260803_172528_009.png` | q1 |
| `MX-M3658N_20260803_172528_009.png` | q2 |
| `MX-M3658N_20260803_172528_009.png` | q3 |
| `MX-M3658N_20260803_172528_009.png` | q4 |
| `MX-M3658N_20260803_172528_009.png` | q5 |
| `MX-M3658N_20260803_172528_009.png` | q6 |
| `MX-M3658N_20260803_172528_009.png` | q7 |
| `MX-M3658N_20260803_172528_009.png` | q8 |
| `MX-M3658N_20260803_172528_009.png` | q10 |
| `MX-M3658N_20260803_172528_009.png` | q11 |
| `MX-M3658N_20260803_172528_010.png` | q4 |
| `MX-M3658N_20260803_172528_010.png` | q5 |
| `MX-M3658N_20260803_172528_010.png` | q6 |
| `MX-M3658N_20260803_172528_011.png` | q1 |
| `MX-M3658N_20260803_172528_011.png` | q6 |
| `MX-M3658N_20260803_172528_015.png` | id1 |
| `MX-M3658N_20260803_172528_015.png` | id3 |
| `MX-M3658N_20260803_172528_015.png` | id4 |
| `MX-M3658N_20260803_172528_015.png` | id5 |
| `MX-M3658N_20260803_172528_015.png` | q3 |
| `MX-M3658N_20260803_172528_015.png` | q4 |
| `MX-M3658N_20260803_172528_015.png` | q8 |
| `MX-M3658N_20260803_172528_016.png` | q1 |
| `MX-M3658N_20260803_172528_016.png` | q2 |
| `MX-M3658N_20260803_172528_016.png` | q4 |
| `MX-M3658N_20260803_172528_016.png` | q6 |
| `MX-M3658N_20260803_172528_016.png` | q7 |
| `MX-M3658N_20260803_172528_016.png` | q8 |
| `MX-M3658N_20260803_172528_016.png` | q9 |
| `MX-M3658N_20260803_172528_016.png` | q10 |
| `MX-M3658N_20260803_172528_016.png` | q11 |
| `MX-M3658N_20260803_172528_017.png` | id3 |
| `MX-M3658N_20260803_172528_017.png` | id4 |
| `MX-M3658N_20260803_172528_017.png` | q4 |
| `MX-M3658N_20260803_172528_017.png` | q5 |
| `MX-M3658N_20260803_172528_020.png` | id1 |
| `MX-M3658N_20260803_172528_020.png` | id3 |
| `MX-M3658N_20260803_172528_020.png` | id6 |
| `MX-M3658N_20260803_172528_020.png` | q1 |
| ... | 9 more rows in BlankCells.csv |