# New inputs recognition run with rebuilt template v3

Date: 2026-08-03

## Scope

This archive records a local command-line recognition run for the replaced answer sheets in `inputs/` using a newly generated reference/template for this batch. It does not reuse or modify the archived four-scenario template or prior regression archives.

This v3 template supersedes v2 for this new-input batch. The key adjustment from v2 is that `q10`, `q12`, and `q14` were shifted upward by 12 pixels after local crop scanning showed their answer bubbles were centered above the previous coordinates.

## Template/reference

Archived template directory:

- `docs/assets/templates/new-inputs-20260803-172528-v3/`
- Reference: `reference.png`, generated from `MX-M3658N_20260803_172528_001.pdf` at 144 DPI
- Template: `template.json`

Template shape:

- 8 ID digit columns: `id1` through `id8`
- 8 single-choice fields: `q1` through `q8`
- 7 multi-choice fields: `q9` through `q15`

Coordinate adjustment from v2:

| Field | v2 origin | v3 origin |
| --- | --- | --- |
| `q10` | `[121, 802]` | `[121, 790]` |
| `q12` | `[323, 802]` | `[323, 790]` |
| `q14` | `[526, 802]` | `[526, 790]` |

## Recognition command

```cmd
python main.py -i inputs -o outputs\new-inputs-20260803-172528-new-template-v3
```

## Archived results

Archived output directory:

- `docs/assets/regression-results/2026-08-03-new-inputs-172528-new-template-v3/`

Key files:

- `Results/Results_05PM.csv`
- `Results/WeakFillReview.csv`
- `Manual/ErrorFiles.csv`
- `Manual/MultiMarkedFiles.csv`
- `CheckedOMRs/*.png`

## Recognition summary

The run processed 20 answer-sheet PDFs and produced 23 output fields per sheet, for 460 total field values.

| Metric | v2 | v3 |
| --- | ---: | ---: |
| Rows processed | 20 | 20 |
| Output fields per row | 23 | 23 |
| Total field values | 460 | 460 |
| Blank fields | 40 | 10 |
| Invalid-format fields | 3 | 3 |
| Nonblank rate | 91.30% | 97.83% |
| Valid-format rate | 90.65% | 97.17% |

Validation rules used for the summary:

- `id1..id8`: exactly one digit
- `q1..q8`: exactly one option from `A-D`
- `q9..q15`: one or more unique options from `A-D`

## Focus-field improvement

| Field | v2 blanks | v3 blanks |
| --- | ---: | ---: |
| `q10` | 18 | 0 |
| `q12` | 6 | 0 |
| `q14` | 6 | 0 |

## Remaining audit/review notes

`Results/WeakFillReview.csv` was generated and archived. It includes resolved weak ID candidates, low-confidence ID candidates, one weak mark candidate, and single-choice conflict records.

Remaining invalid-format records observed in the result CSV:

| File | Field | Value | Note |
| --- | --- | --- | --- |
| `MX-M3658N_20260803_172528_010.png` | `q7` | `AC` | Single-choice conflict, review candidate `C` |
| `MX-M3658N_20260803_172528_010.png` | `q8` | `BD` | Single-choice conflict, review candidate `B` |
| `MX-M3658N_20260803_172528_017.png` | `id8` | `34` | ID digit conflict |

Remaining blanks are not in `q10`, `q12`, or `q14`. They are concentrated in one low-confidence/blank ID sheet and one weak `q3` mark. These should be manually reviewed against the archived checked OMR images if perfect field completion is required.

## Conclusion

The q10/q12/q14 coordinate adjustment fixed the major missing-recognition issue for those fields. v3 is the recommended template for the `MX-M3658N_20260803_172528_*` input batch.
