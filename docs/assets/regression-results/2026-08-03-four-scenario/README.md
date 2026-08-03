# 2026-08-03 Four-scenario Local Regression Results

This directory archives the local non-web OMR regression statistics generated for the four answer-card scenes in `docs/assets`.

## Source command

```cmd
python scripts\run_omr_regression.py
```

## Archived reports

- `recognition_rate_report.md`: Markdown summary with recognition rates, blank cells, fallback/review counts, and review details.
- `recognition_rate_report.csv`: machine-readable summary with scenario-level recognition rates and review statistics.
- `Results/*_Results.csv`: scenario-named recognition result CSV files.
- `Results/*_WeakFillReview.csv`: scenario-named review/audit CSV files, when the scene produced review records.

## Scope

Archived scenes:

- `weak` / `淡涂答题卡归档`
- `normal` / `正常填涂测试答题卡归档`
- `underfill` / `没涂满答题卡归档`
- `overflow` / `涂超出答题卡归档`

## Notes

- This archive stores statistics and CSV outputs only.
- Large generated checked OMR images under `outputs/<scenario>/CheckedOMRs` are intentionally not archived.
- The matching template configuration is archived at `docs/assets/templates/omr-four-scenario/`.
