
## Multi-select Full-select Fallback

A later 21-sheet validation set exposed a valid multi-select case where all four options are filled. For `MX-M3658N_20260731_123655_007.png`, `q10` was visually `ABCD`, but the four options were all weak and similar:

```text
q10 A-D means: 146.77, 141.80, 139.20, 142.56
local/global threshold: 120.85
normal detected options: none
```

The existing weak multi-select fallback estimates a blank baseline from the lighter half of A-D. That is safe for partially selected rows, but it is not reliable when every option is filled because there may be no blank option in the row.

The added full-select fallback is intentionally stricter than the existing weak multi-select fallback:

1. It is disabled by default in global defaults.
2. It only runs when `weak_multi_mark_params.enabled=true`.
3. It only runs for configured multi-select `labels`, for example `q9`, `q10`, `q11`.
4. It only runs when normal detection found no options.
5. It only runs after the existing weak multi-select fallback found no candidates.
6. It returns all options only when every option is dark enough and the row is internally consistent.
7. It uses both a fixed darkness guard and a page-relative guard to reduce blank-row false positives.

Additional config fields:

```json
"weak_multi_mark_params": {
  "enabled": true,
  "labels": ["q9", "q10", "q11"],
  "only_when_blank": true,
  "min_delta_from_blank": 10,
  "max_mean": 218,
  "max_marks": 4,
  "full_select_fallback_enabled": true,
  "full_select_max_mean": 170,
  "full_select_global_surplus": 30,
  "full_select_max_spread": 25
}
```

Field meaning:

- `full_select_fallback_enabled`: Enables the full-select fallback for weak all-options-filled rows.
- `full_select_max_mean`: All option means must be at or below this fixed darkness limit.
- `full_select_global_surplus`: All option means must also be at or below `global_thr + full_select_global_surplus`.
- `full_select_max_spread`: The difference between darkest and lightest option in the row must be at or below this value.

Blank-row false-positive control:

- A truly unfilled row can also have low spread, so spread alone is not enough.
- The fallback therefore requires all options to be dark enough by absolute mean and by page-relative threshold.
- On the 21-sheet validation set the fallback logged exactly one event:

```text
Weak multi full-select fallback: field 'q10' -> 'ABCD' (max_mean=146.77, max_allowed_mean=150.85, spread=7.57)
```

Validation command:

```bash
python main.py -i inputs -o outputs_inputs_21_full_select_guarded
```

Validation result:

```text
rows 21
id_blank_cells 0
id_blank_rows 0
q_blank_cells 0
any_blank_rows 0
MX-M3658N_20260731_123655_007.png q10=ABCD
```

Compared with the feature-alignment-only run, the answer columns changed only here:

```text
MX-M3658N_20260731_123655_007.png q10 '' -> 'ABCD'
```
