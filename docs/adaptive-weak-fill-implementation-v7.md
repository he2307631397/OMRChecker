# Adaptive Weak-fill Implementation v7

## Branch

```text
weak-fill-enhancement
```

## Purpose

Implement the P0 recommendations from:

```text
docs/adaptive-weak-fill-design.md
docs/Adaptive_OMR_Weak_Fill_Optimization_Recommendations.md
docs/adaptive-weak-fill-recommendations-feasibility.md
```

The implementation keeps the normal recognition path unchanged and applies adaptive fallback only to fields that are blank after normal recognition.

## Implemented P0 Features

### Shared diagnostics

Added reusable diagnostics in `src/core.py`:

- Page blank model from the lighter page-level bubble distribution.
- Field-level local blank baseline.
- Darkest candidate mean.
- Second-darkest candidate mean.
- Gap between the darkest and second-darkest candidates.
- Delta from local blank baseline.
- Delta from page blank baseline.
- Page z-score.
- Inner-ROI dark-pixel density.
- Density gap versus other candidates.

### Single-choice fallback

Single-choice fallback now uses the shared diagnostic model, but remains conservative.

It still applies only when:

- Normal recognition is blank.
- Field type is in `weak_mark_params.supported_field_types`.
- The field is not template-level `multiSelect`.
- The label is not excluded.

Current result: it logs weak single-choice candidates but does not recover the current 3 ambiguous weak-fill answer blanks because their local candidate separation is weak.

This is intentional for this implementation stage. A more aggressive page-model-only answer recovery was tested and reduced `q_blank_cells` to 0, but it produced questionable candidate directions for low-gap fields. That approach was not kept as the committed strategy.

### Identifier fallback

Identifier fallback now has two paths:

1. Strict rule:
   - Original `max_mean` cap.
   - Original `min_gap`.
   - Original `min_delta_from_blank`.

2. Adaptive rule:
   - `adaptive_max_mean` cap.
   - `adaptive_min_gap`.
   - `adaptive_min_delta_from_blank`.
   - Page z-score.
   - Dark-pixel density.
   - Density gap.

This lets weak identifier fills slightly above the old absolute `max_mean` pass only when multiple adaptive signals agree.

Identifier fallback remains separate from answer fallback because identity fields have higher error cost.

## Configuration Changes

### `weak_mark_params`

New guardrail fields:

```json
{
  "min_delta_from_blank": 25,
  "adaptive_min_delta_from_blank": 12,
  "min_delta_from_page_blank": 20,
  "min_page_z_score": 1.5,
  "min_dark_pixel_ratio": 0.04,
  "min_density_gap": 0.01
}
```

### `weak_identifier_params`

New adaptive fields:

```json
{
  "adaptive_min_gap": 10,
  "adaptive_min_delta_from_blank": 15,
  "min_page_z_score": 1.5,
  "min_dark_pixel_ratio": 0.04,
  "min_density_gap": 0.01,
  "adaptive_max_mean": 210
}
```

Defaults remain disabled. The current `inputs/config.json` explicitly enables weak fallback families for the current test input.

## Validation: 10 Weak-fill Sheets

Command:

```bash
python main.py -i inputs -o outputs_inputs_10_weak_fill_adaptive_v7
```

Log:

```text
weak_fill_adaptive_10_v7.log
```

Result CSV:

```text
outputs_inputs_10_weak_fill_adaptive_v7/Results/Results_04PM.csv
```

Summary:

```text
rows=10
id_blank_cells=1
q_blank_cells=3
blank_cells=4
blank_rows=4
```

Remaining blank fields:

```text
MX-M3658N_20260731_162311_001.png q5
MX-M3658N_20260731_162311_004.png id7
MX-M3658N_20260731_162311_008.png q3
MX-M3658N_20260731_162311_009.png q6
```

Compared with the pre-adaptive weak-fill test in `docs/weak-fill-10-test.md`:

```text
Before:
rows=10
id_blank_cells=12
q_blank_cells=3
blank_cells=15
blank_rows=6

After v7:
rows=10
id_blank_cells=1
q_blank_cells=3
blank_cells=4
blank_rows=4
```

Main improvement:

```text
identifier blanks: 12 -> 1
all blanks: 15 -> 4
```

Answer blanks remain unchanged because the current three blank answer fields have weak local separation. A more aggressive page-model-only recovery was tested but not accepted as safe enough for this stage.

## Fallback Log Summary

v7 fallback logs show identifier recoveries only:

```text
Weak identifier fallback: 11
Weak mark fallback: 0
```

No weak single-choice answer fallback was accepted in v7.

## Normal-fill 56-sheet Regression Status

Not yet run in this session because the current `inputs/` directory contains only the 10 weak-fill PDFs:

```text
MX-M3658N_20260731_162311_001.pdf .. _010.pdf
```

The 56-sheet normal-fill regression must be run before merging this branch back to `robyn-web-service`.

Required regression command after restoring the 56-sheet input set:

```bash
python main.py -i inputs -o outputs_inputs_56_adaptive_regression
```

Required non-regression target from `docs/normal-fill-56-baseline.md`:

```text
rows=56
id_blank_cells=0
q_blank_cells=0
blank_rows=0
```

The branch must not be merged until this regression passes and any CSV differences are reviewed.

## Risk Notes

- The identifier improvement is promising because remaining weak identifier candidates had high density and strong page z-score, but identity fields remain sensitive.
- The answer weak-fill problem likely needs a review CSV or manual confirmation loop before accepting page-model-only recovery.
- The current implementation logs rejected weak candidates at `INFO` level for audit. This is useful during branch validation and can be reduced later if logs become too noisy.

## Current Recommendation

Keep this implementation on `weak-fill-enhancement` only.

Do not merge to `robyn-web-service` yet.

Next steps:

1. Restore or obtain the 56-sheet normal-fill input set.
2. Run the 56-sheet non-regression test.
3. Compare against `docs/normal-fill-56-baseline.md`.
4. If the 56-sheet baseline passes, decide whether to add `adaptive_review.csv` before merge.
5. Revisit the three remaining answer blanks with manual visual confirmation before enabling more aggressive answer fallback.
