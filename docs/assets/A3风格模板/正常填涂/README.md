# A3 Style Normal-fill Template Snapshot

This directory stores the generated OMR template for `docs/assets/A3风格模板/正常填涂/`.

## Archived files

- `reference.png`: rendered from `MX-M3658N_20260803_180706_001.pdf` at `pdf_dpi=144`.
- `config.json`: A3 landscape processing dimensions, PDF rendering, weak mark support, and automatic alignment enabled.
- `template.json`: choice-question bubbles for `q1` through `q11`, with `q9` through `q11` enabled as multi-select.

## Preprocessing

The template enables `FeatureBasedAlignment` against `reference.png`, and `config.json` sets `alignment_params.auto_align=true` for the built-in alignment adjustment.

## Recognition command

```cmd
python main.py -i "docs\assets\A3风格模板\正常填涂" -o outputs\a3-style-normal-fill-template
```
