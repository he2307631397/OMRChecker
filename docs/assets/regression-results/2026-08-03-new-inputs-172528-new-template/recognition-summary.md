# New inputs recognition run with rebuilt template

Date: 2026-08-03

## Scope

This archive records a local command-line recognition run for the replaced answer sheets in `inputs/` using a newly generated reference/template for this batch. It does not reuse or modify the archived four-scenario template or prior regression archives.

## Template/reference

Archived template directory:

- `docs/assets/templates/new-inputs-20260803-172528-v2/`
- Reference: `reference.png`, generated from `MX-M3658N_20260803_172528_001.pdf` at 144 DPI
- Template: `template.json`

Template shape:

- 8 ID digit columns: `id1` through `id8`
- 8 single-choice fields: `q1` through `q8`
- 7 multi-choice fields: `q9` through `q15`

## Recognition command

```cmd
python main.py -i inputs -o outputs\new-inputs-20260803-172528-new-template-v2
```

## Archived results

Archived output directory:

- `docs/assets/regression-results/2026-08-03-new-inputs-172528-new-template/`

Key files:

- `Results/Results_05PM.csv`
- `Results/WeakFillReview.csv`
- `Manual/ErrorFiles.csv`
- `Manual/MultiMarkedFiles.csv`
- `CheckedOMRs/*.png`

## Recognition summary

The run processed 20 answer-sheet PDFs and produced 23 output fields per sheet, for 460 total field values.

| Metric | Value |
| --- | ---: |
| Rows processed | 20 |
| Output fields per row | 23 |
| Total field values | 460 |
| Blank fields | 40 |
| Invalid-format fields | 3 |
| Nonblank rate | 91.30% |
| Valid-format rate | 90.65% |

Validation rules used for the summary:

- `id1..id8`: exactly one digit
- `q1..q8`: exactly one option from `A-D`
- `q9..q15`: one or more unique options from `A-D`

## Audit/review notes

`Results/WeakFillReview.csv` was generated and archived. It includes resolved weak ID candidates, low-confidence ID candidates, weak mark candidates, and single-choice conflict records.

Invalid-format records observed in the result CSV:

| File | Field | Value | Note |
| --- | --- | --- | --- |
| `MX-M3658N_20260803_172528_010.png` | `q7` | `AC` | Single-choice conflict, review candidate `C` |
| `MX-M3658N_20260803_172528_010.png` | `q8` | `BD` | Single-choice conflict, review candidate `B` |
| `MX-M3658N_20260803_172528_017.png` | `id8` | `34` | ID digit conflict |

Blank fields are concentrated in unanswered/low-confidence fields, especially `q10`, `q14`, and one sheet with blank ID fields. These should be manually reviewed against the archived checked OMR images if perfect field completion is required.

## Comparison with old-template baseline

A prior diagnostic baseline using the old archived template on the same new inputs showed poor fit:

| Run | Nonblank rate | Valid-format rate | Blank fields | Invalid-format fields |
| --- | ---: | ---: | ---: | ---: |
| Old-template diagnostic baseline | 76.58% | 22.63% | 89 | 205 |
| Rebuilt new-card template v2 | 91.30% | 90.65% | 40 | 3 |

The rebuilt template is the appropriate working template/reference for this replaced answer-sheet batch.
