# Weak-fill recognition test with v3 new-card template

Date: 2026-08-04

## Scope

This archive records a local command-line recognition run for the weak-fill test answer sheets currently placed in `inputs/`.

Input batch:

- `MX-M3658N_20260804_145800_001.pdf` through `MX-M3658N_20260804_145800_010.pdf`

Template/reference used:

- Current local `inputs/template.json` and `inputs/reference.png`
- This is the v3 new-card template shape previously archived at `docs/assets/templates/new-inputs-20260803-172528-v3/`

## Recognition command

```cmd
python main.py -i inputs -o outputs\weak-fill-20260804-145800-v3-template
```

## Archived results

Archived output directory:

- `docs/assets/regression-results/2026-08-04-weak-fill-145800-v3-template/`

Key files:

- `Results/Results_05PM.csv`
- `Results/WeakFillReview.csv`
- `Manual/ErrorFiles.csv`
- `Manual/MultiMarkedFiles.csv`
- `CheckedOMRs/*.png`

## Recognition summary

The run processed 10 weak-fill answer-sheet PDFs and produced 23 output fields per sheet, for 230 total field values.

| Metric | Value |
| --- | ---: |
| Rows processed | 10 |
| Output fields per row | 23 |
| Total field values | 230 |
| Blank fields | 26 |
| Invalid-format fields | 0 |
| Nonblank rate | 88.70% |
| Valid-format rate | 88.70% |

Validation rules used for the summary:

- `id1..id8`: exactly one digit
- `q1..q8`: exactly one option from `A-D`
- `q9..q15`: one or more unique options from `A-D`

## Group-level result

| Group | Nonblank | Total | Nonblank rate | Blanks |
| --- | ---: | ---: | ---: | ---: |
| ID digits `id1..id8` | 56 | 80 | 70.00% | 24 |
| Single-choice `q1..q8` | 78 | 80 | 97.50% | 2 |
| Multi-choice `q9..q15` | 70 | 70 | 100.00% | 0 |

## Blank-field distribution

| Field | Blank count |
| --- | ---: |
| `id4` | 9 |
| `id1` | 7 |
| `id3` | 6 |
| `id2` | 1 |
| `id8` | 1 |
| `q5` | 1 |
| `q8` | 1 |

## Focus fields

The fields that were previously adjusted in v3 remain stable on this weak-fill batch:

| Field | Blank count |
| --- | ---: |
| `q10` | 0 |
| `q12` | 0 |
| `q14` | 0 |

## Review/audit summary

`Results/WeakFillReview.csv` was generated and archived.

| Review type | Count |
| --- | ---: |
| `ID_REVIEW` | 29 |
| `WEAK_MARK_REVIEW` | 2 |

| Review status | Count |
| --- | ---: |
| `RESOLVED_CANDIDATE` | 5 |
| `LOW_CONFIDENCE` | 24 |
| `LEGACY` | 2 |

The weak-fill cards are recognized well for the objective answer areas. Remaining misses are concentrated in the ID bubble area, especially `id1`, `id3`, and `id4`, with two weak single-choice marks (`q5`, `q8`) left for manual review.
