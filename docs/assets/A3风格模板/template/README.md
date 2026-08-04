# A3 Style Template Snapshot

This directory archives the answer-sheet template files confirmed by the 2026-08-04 A3 style normal-fill recognition run.

Template category: `A3风格模板/正常填涂`.

## Archived files

- `config.json`
- `template.json`
- `reference.png`

## Source and scope

The files were copied from `docs/assets/A3风格模板/正常填涂/` after the recognition result was confirmed as perfect.

The reference image was rendered from:

- `docs/assets/A3风格模板/正常填涂/MX-M3658N_20260803_180706_001.pdf`

Covered input batch:

- `MX-M3658N_20260803_180706_001.pdf` through `MX-M3658N_20260803_180706_010.pdf`

## Related recognition archive

The corresponding recognition results are archived at:

- `docs/assets/regression-results/2026-08-04-a3-style-normal-fill-template/`

Recognition command:

```cmd
python -X utf8 main.py -i "docs\assets\A3风格模板\正常填涂" -o outputs\a3-style-normal-fill-template
```

Notes:

- `template.json` recognizes `q1..q11`.
- `q9..q11` are configured as multi-select.
- `FeatureBasedAlignment` uses `reference.png`.
- `config.json` enables `alignment_params.auto_align=true`.
