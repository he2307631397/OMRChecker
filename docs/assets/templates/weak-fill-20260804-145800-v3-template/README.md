# Weak Fill 20260804 145800 v3 Template Snapshot

This directory archives the answer-sheet template files used for the local weak-fill recognition verification run on 2026-08-04.

## Archived files

- `config.json`
- `template.json`
- `reference.png`

## Source and scope

The files were copied from the current local `inputs/` directory after validating the weak-fill answer-sheet batch:

- `MX-M3658N_20260804_145800_001.pdf` through `MX-M3658N_20260804_145800_010.pdf`

This template is the v3 new-card template shape that was previously archived at `docs/assets/templates/new-inputs-20260803-172528-v3/` and was reused for the 2026-08-04 weak-fill validation.

## Related recognition archive

The corresponding recognition results are archived at:

- `docs/assets/regression-results/2026-08-04-weak-fill-145800-v3-template/`

Recognition command:

```cmd
python main.py -i inputs -o outputs\weak-fill-20260804-145800-v3-template
```

Summary: objective answer areas remained stable, with remaining misses concentrated in ID bubbles and two weak single-choice marks left for manual review.
