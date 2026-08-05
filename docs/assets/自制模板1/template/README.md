# OMR Four-scenario Template Archive

This directory archives the OMR template configuration currently used by the local four-scenario regression test over `docs/assets`.

## Purpose

`inputs/` is a runtime working directory and is ignored by git. This archive keeps the current template files in a tracked location so the regression can be reproduced later.

## Archived files

- `config.json`: recognition tuning parameters, PDF rendering parameters, output settings, weak-fill and review settings.
- `template.json`: A4 answer sheet layout, ID fields, single-choice fields, multi-select fields, and preprocessing configuration.
- `reference.png`: reference image used by `FeatureBasedAlignment`.

## Covered test scenes

The template is intended for these answer-card scenes under `docs/assets`:

- `正常填涂测试答题卡归档`
- `淡涂答题卡归档`
- `没涂满答题卡归档`
- `涂超出答题卡归档`

## Restore to runtime inputs

From the repository root on Windows:

```cmd
python -c "from pathlib import Path; import shutil; src=Path('docs/assets/templates/omr-four-scenario'); dst=Path('inputs'); dst.mkdir(exist_ok=True); [shutil.copy2(src/name, dst/name) for name in ['config.json','template.json','reference.png']]"
```

Optional, copy this note too:

```cmd
copy docs\assets\templates\omr-four-scenario\README.md inputs\README.md
```

## Local regression command

```cmd
python scripts\run_omr_regression.py
```

Outputs are generated under `outputs/`, including scenario-named CSV files and recognition-rate reports.

## Notes

- This template assumes the current A4 single-page PDF layout and `pdf_dpi=144`.
- If the sheet layout, scan scaling, or bubble coordinates change, recalibrate `template.json` and update this archive.
- This archive intentionally does not include generated outputs.
