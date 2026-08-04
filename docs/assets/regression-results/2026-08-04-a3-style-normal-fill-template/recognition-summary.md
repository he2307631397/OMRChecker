# A3 Style Normal-fill Recognition Run

Date: 2026-08-04

## Scope

This archive records a local recognition run for the A3 style normal-fill answer sheets in `docs/assets/A3风格模板/正常填涂/`.

Input batch:

- `MX-M3658N_20260803_180706_001.pdf` through `MX-M3658N_20260803_180706_010.pdf`

Template/reference used:

- `docs/assets/A3风格模板/正常填涂/template.json`
- `docs/assets/A3风格模板/正常填涂/config.json`
- `docs/assets/A3风格模板/正常填涂/reference.png` rendered from `_001.pdf` at `pdf_dpi=144`

## Recognition command

```cmd
python -X utf8 main.py -i "docs\assets\A3风格模板\正常填涂" -o outputs\a3-style-normal-fill-template
```

## Archived results

Archived output directory:

- `docs/assets/regression-results/2026-08-04-a3-style-normal-fill-template/`

Key files:

- `Results/Results_05PM.csv`
- `Results/WeakFillReview.csv`
- `Manual/ErrorFiles.csv`
- `Manual/MultiMarkedFiles.csv`
- `CheckedOMRs/*.png`

## Recognition summary

| Metric | Value |
| --- | ---: |
| Rows processed | 10 |
| Output fields per row | 11 |
| Total field values | 110 |
| Nonblank fields | 110 |
| Nonblank rate | 100.00% |
| Multi-select fields with multiple marks (`q9..q11`) | 30 |

The first pass recognizes the visible choice area (`q1..q11`) and leaves written-answer regions out of OMR extraction.
