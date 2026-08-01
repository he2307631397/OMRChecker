# Single-choice Conflict Resolution

## Context

After adaptive weak-fill v7, the 10-sheet weak-fill batch improved identifier blanks substantially, but manual review found structurally invalid single-choice outputs.

Examples from v7:

```text
MX-M3658N_20260731_162311_001.png q1 ABCD
MX-M3658N_20260731_162311_001.png q2 ABD
MX-M3658N_20260731_162311_002.png q2 ABD
MX-M3658N_20260731_162311_003.png q2 ABD
MX-M3658N_20260731_162311_004.png q2 ABCD
```

These fields are `QTYPE_MCQ4` and are not marked `multiSelect`. Therefore returning more than one option is invalid even if the main threshold detects multiple dark bubbles.

The existing legal multi-select fields remain:

```text
q9, q10, q11
```

They are template-level `multiSelect=true` and are not affected by this change.

## Implementation

Added `resolve_single_choice_conflict()` in `src/core.py`.

It runs after normal threshold detection and before writing detected bubbles into `omr_response`.

It applies only when:

- `weak_mark_params.resolve_single_choice_conflicts=true`
- field type is in `weak_mark_params.supported_field_types`
- field is not `multiSelect`
- more than one bubble was detected by the main threshold
- field label is not excluded

Decision:

1. Compute field diagnostics using the same adaptive helper:
   - darkest candidate
   - second-darkest candidate
   - gap
   - local blank baseline
   - delta from blank
2. If the darkest candidate has enough separation, keep only the darkest candidate.
3. If separation is too weak, output blank instead of an invalid multi-choice string.
4. Log every resolved or unresolved conflict.

This follows the principle:

```text
For single-choice fields, one high-confidence candidate is acceptable.
A multi-option answer is structurally invalid.
An unresolved conflict should stay blank for review.
```

## Configuration

New `weak_mark_params` fields:

```json
{
  "resolve_single_choice_conflicts": true,
  "conflict_min_gap": 5,
  "conflict_min_delta_from_blank": 12
}
```

Defaults are disabled in `src/defaults/config.py`. The current `inputs/config.json` enables this for the weak-fill test branch.

## Validation

Command:

```bash
python main.py -i inputs -o outputs_inputs_10_single_conflict_v1
```

Log:

```text
single_conflict_v1.log
```

Result CSV:

```text
outputs_inputs_10_single_conflict_v1/Results/Results_05PM.csv
```

Summary:

```text
rows=10
id_blank_cells=1
q_blank_cells=3
single_multi_count=0
```

Remaining single-choice blanks:

```text
MX-M3658N_20260731_162311_001.png q5
MX-M3658N_20260731_162311_008.png q3
MX-M3658N_20260731_162311_009.png q6
```

Compared with v7:

```text
v7 single_multi_count=5
v1 single_multi_count=0
```

Identifier performance stayed the same:

```text
id_blank_cells=1
```

## Current Status

This fixes the invalid single-choice multi-output issue without changing legal multi-select behavior.

The remaining problem is the three single-choice blanks. Earlier testing showed that forcing them with page-level evidence alone can reduce blanks, but it risks choosing the wrong option when local candidate separation is weak.

Next recommended step:

- Add `adaptive_review.csv` for low-confidence single-choice blanks.
- Manually confirm q5/q3/q6 on the current weak-fill images.
- Only then decide whether to enable a second-tier reviewable recovery for these fields.

## Merge Gate

Do not merge to `robyn-web-service` until the 56-sheet normal-fill regression is restored and passes:

```text
rows=56
id_blank_cells=0
q_blank_cells=0
single_multi_count=0 for non-multiSelect fields
```
