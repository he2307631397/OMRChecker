# Weak Mark Detection Optimization

## Background

Some scanned OMR sheets contain very lightly filled boxes. In the current implementation, each bubble is classified by comparing the mean grayscale value of the configured bubble ROI against a local threshold. This works for normal fills, but lightly filled boxes can have mean values close to blank boxes.

Observed example from `inputs/MX-M3658N_20260730_123704_003.pdf` at 144 DPI:

```text
Q6:  A 225.56, B 209.32, C 225.74, D 222.17
Q9:  A 229.83, B 214.66, C 211.64, D 224.71
Q10: A 210.56, B 226.15, C 226.91, D 200.34
Local/global threshold: around 200
```

The likely answers are still relatively darker than the other options, but not dark enough to cross the normal threshold. Lowering the global threshold would increase false positives, especially for blank answers and noisy scans.

## Goal

Improve recall for lightly filled single-choice questions without changing the default behavior or increasing false positives for normal forms.

## Proposed Strategy

Add an optional weak-mark fallback after the existing threshold logic:

1. Run the current threshold-based detection first.
2. If a field has no detected bubble, consider a weak-mark fallback.
3. Restrict fallback to horizontal single-choice fields only, for example `QTYPE_MCQ4`.
4. Compute the darkest and second-darkest bubble ROI mean values in the field.
5. If the darkest option is sufficiently darker than the second-darkest option, select it as a weak mark.
6. Log the recovered answer with diagnostic values.

This avoids changing strong normal detections and only acts when the original result would be blank.

## Risk Controls

The fallback must be conservative:

- Disabled by default for upstream compatibility unless enabled in `config.json`.
- Only applies when the current algorithm detected no bubble.
- Only applies to single-choice fields, not roll numbers or multi-select fields.
- Requires a minimum contrast between the darkest and second-darkest options.
- Optionally requires the darkest option to be below an absolute maximum mean value, so very clean blank rows are not forced into an answer.
- Logs every weak recovery so downstream review is possible.

## Configuration

Suggested config section:

```json
"weak_mark_params": {
  "enabled": true,
  "min_gap": 10,
  "max_mean": 215,
  "supported_field_types": ["QTYPE_MCQ4"]
}
```

Field meaning:

- `enabled`: Enables or disables fallback.
- `min_gap`: Required mean difference between second-darkest and darkest option.
- `max_mean`: Darkest option must be at or below this value.
- `supported_field_types`: Field types eligible for fallback.

## Expected Effect on Current Inputs

For the abnormal third PDF:

- Q6 can likely be recovered as B because B is darker than A/C/D by about 13-16 points.
- Q9 may be ambiguous because B and C are both weak and close. If the gap is too small, it should remain blank or be flagged for review.
- Q10 may be recovered as D only if the max-mean guard permits it. Since D is around 200.34, it is borderline but plausible.

## Validation Result on Current Inputs

Validation commands:

```bash
python main.py --inputDir inputs --outputDir outputs_inputs_pdf_weak_mark_verify
```

Baseline output was generated with the same 144 DPI template before enabling weak-mark fallback. The weak-mark run produced exactly one answer change:

```text
MX-M3658N_20260730_123704_003.png q6 '' -> 'B'
```

The full output row for the abnormal third PDF after the fallback is:

```csv
"file_id","id1","id2","id3","id4","id5","id6","id7","id8","q1","q2","q3","q4","q5","q6","q7","q8","q9","q10","q11"
"MX-M3658N_20260730_123704_003.png","2","5","0","4","0","3","1","1","C","A","B","A","B","B","D","D","","","D"
```

Runtime log for the recovered field:

```text
Weak mark fallback: field 'q6' -> 'B' (darkest_mean=209.15, second_darkest_mean=222.04, gap=12.90)
```

No other fields changed compared with the 144 DPI baseline.

Important: `q9`, `q10`, and `q11` are multi-select questions on the current sheet, so they are intentionally excluded in `inputs/config.json`. This keeps ambiguous multi-select weak marks from being forced into single-choice answers.

## Follow-up Ideas

If this is not enough, further improvements can include:

- Use only the inner 60-70% of the bubble ROI to reduce border-line noise.
- Combine mean intensity with dark-pixel ratio.
- Emit a separate low-confidence column or report for manual review.
- Add per-template weak-mark tuning values.

## Multi-select Weak Mark Extension Plan

The single-choice fallback intentionally selects at most one darkest option. Multi-select questions should not reuse that exact rule because multiple answers can be valid, and forcing only the darkest option would lose valid weak marks.

For current inputs, `q9`, `q10`, and `q11` are multi-select questions. The observed problematic fields are `q9` and `q10` in `MX-M3658N_20260730_123704_003.pdf`:

```text
Q9:  A 229.83, B 214.66, C 211.64, D 224.71
Q10: A 210.56, B 226.15, C 226.91, D 200.34
```

Recommended multi-select strategy:

1. Run the existing threshold detection first.
2. Keep all strongly detected options.
3. If the result is blank or missing weak options, evaluate each option independently.
4. Estimate the blank baseline for the row from the lighter options, for example median or high percentile of A-D means.
5. Append any option whose mean is sufficiently darker than that blank baseline.
6. Apply conservative guards to avoid over-selecting blank boxes.
7. Log every weak option that is appended.

Suggested config section:

```json
"weak_multi_mark_params": {
  "enabled": true,
  "labels": [],
  "only_when_blank": true,
  "min_delta_from_blank": 10,
  "max_mean": 218,
  "max_marks": 4
}
```

Template marking for multi-select questions:

```json
"Q10": {
  "fieldType": "QTYPE_MCQ4",
  "fieldLabels": ["q10"],
  "multiSelect": true,
  "bubbleDimensions": [29, 18],
  "bubblesGap": 39,
  "labelsGap": 0,
  "origin": [337, 933]
}
```

When the number of multi-select questions changes, add or remove `"multiSelect": true` on the corresponding `fieldBlocks`. The global `labels` list can stay empty.

Field meaning:

- `enabled`: Enables or disables multi-select fallback.
- `labels`: Optional compatibility override for field labels eligible for multi-select weak fallback. Prefer leaving it empty and marking multi-select field blocks with `"multiSelect": true` in `template.json`.
- `only_when_blank`: Only apply fallback when the normal detector found no options for the question.
- `min_delta_from_blank`: Required difference between estimated blank baseline and option mean.
- `max_mean`: Candidate option must be at or below this value.
- `max_marks`: Maximum number of total selected options allowed after fallback.

Expected effect on current abnormal third PDF with conservative settings and `only_when_blank=true`:

- `q9`: likely recovers `BC`, because B and C are darker than A/D by about 10-18 points.
- `q10`: likely recovers `AD`, because A and D are darker than B/C by about 16-26 points.
- `q11`: remains normal as `D`, because it is already detected by the existing threshold logic and blank-only fallback does not append extra options.

Risk notes:

- Multi-select fallback can add false positives more easily than single-choice fallback.
- It should only be enabled for known multi-select labels.
- With `only_when_blank=true`, it preserves existing strong detections and only fills questions that would otherwise be blank.
- Validation must compare against the current baseline and verify that non-problematic sheets do not gain extra options unexpectedly.

## Multi-select Validation Result on Current Inputs

Validation command:

```bash
python main.py --inputDir inputs --outputDir outputs_inputs_pdf_weak_multi_blank_only
```

Compared with the single-choice weak-mark run, enabling blank-only multi-select fallback produced exactly two additional changes:

```text
MX-M3658N_20260730_123704_003.png q9 '' -> 'BC'
MX-M3658N_20260730_123704_003.png q10 '' -> 'AD'
```

The third PDF row after both single-choice and multi-select fallback is:

```csv
"file_id","id1","id2","id3","id4","id5","id6","id7","id8","q1","q2","q3","q4","q5","q6","q7","q8","q9","q10","q11"
"MX-M3658N_20260730_123704_003.png","2","5","0","4","0","3","1","1","C","A","B","A","B","B","D","D","BC","AD","D"
```

Runtime logs for multi-select recovery:

```text
Weak multi-mark fallback: field 'q9' -> append 'B' (mean=214.46, blank_baseline=227.15, delta=12.69)
Weak multi-mark fallback: field 'q9' -> append 'C' (mean=211.44, blank_baseline=227.15, delta=15.70)
Weak multi-mark fallback: field 'q10' -> append 'A' (mean=210.33, blank_baseline=226.41, delta=16.08)
Weak multi-mark fallback: field 'q10' -> append 'D' (mean=200.05, blank_baseline=226.41, delta=26.36)
```

`q11` remained `D` and was not expanded to `AD` because `only_when_blank=true` prevents appending weak marks to questions that already have a normal threshold detection.

## Final Review Run Results

Review command:

```bash
python main.py --inputDir inputs --outputDir outputs_inputs_pdf_final_review
```

Result CSV:

```text
outputs_inputs_pdf_final_review/Results/Results_10AM.csv
```

Full recognized results for the five current PDFs:

| file_id | exam_id | q1 | q2 | q3 | q4 | q5 | q6 | q7 | q8 | q9 | q10 | q11 |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| MX-M3658N_20260730_123704_001.png | 27423564 | A | B | C | A | B | C | B | D | AC | BD | AB |
| MX-M3658N_20260730_123704_002.png | 20261224 | D | A | C | B | C | B | A | D | BD | AD | BC |
| MX-M3658N_20260730_123704_003.png | 25040311 | C | A | B | A | B | B | D | D | BC | AD | D |
| MX-M3658N_20260730_124410_001.png | 04236421 | A | B | B | A | C | B | D | D | AB | BC | AD |
| MX-M3658N_20260730_124410_002.png | 25803716 | C | C | C | C | AB | A | D | B | AC | BCD | AC |

Weak fallback events in this run:

```text
Weak mark fallback: field 'q6' -> 'B' (darkest_mean=209.15, second_darkest_mean=222.04, gap=12.90)
Weak multi-mark fallback: field 'q9' -> append 'B' (mean=214.46, blank_baseline=227.15, delta=12.69)
Weak multi-mark fallback: field 'q9' -> append 'C' (mean=211.44, blank_baseline=227.15, delta=15.70)
Weak multi-mark fallback: field 'q10' -> append 'A' (mean=210.33, blank_baseline=226.41, delta=16.08)
Weak multi-mark fallback: field 'q10' -> append 'D' (mean=200.05, blank_baseline=226.41, delta=26.36)
```

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
3. It runs for template field blocks marked with `"multiSelect": true`. The legacy `labels` list is still supported as an explicit override.
4. It only runs when normal detection found no options.
5. It only runs after the existing weak multi-select fallback found no candidates.
6. It returns all options only when every option is dark enough and the row is internally consistent.
7. It uses both a fixed darkness guard and a page-relative guard to reduce blank-row false positives.

Additional config fields:

```json
"weak_multi_mark_params": {
  "enabled": true,
  "labels": [],
  "only_when_blank": true,
  "min_delta_from_blank": 10,
  "max_mean": 218,
  "max_marks": 4,
  "full_select_fallback_enabled": true,
  "full_select_max_mean": 170,
  "full_select_min_delta_from_blank": 35,
  "full_select_max_spread": 25
}
```

Field meaning:

- `full_select_fallback_enabled`: Enables the full-select fallback for weak all-options-filled rows.
- `full_select_max_mean`: All option means must be at or below this fixed darkness limit.
- `full_select_min_delta_from_blank`: The weakest option in an all-selected row must still be this many gray levels darker than the page-level blank bubble baseline.
- `full_select_max_spread`: The difference between darkest and lightest option in the row must be at or below this value.

Blank-row false-positive control:

- A truly unfilled row can also have low spread, so spread alone is not enough.
- The fallback therefore requires all options to be dark enough by absolute mean and by page-relative threshold.
- On the 21-sheet validation set, with `Q9`, `Q10`, and `Q11` marked as `"multiSelect": true` in `template.json` and `labels` left empty, the fallback logged exactly one event. A later 30-sheet scan showed another visually confirmed four-option selection on `MX-M3658N_20260731_153802_015.png q11`; the rule was updated to use the current page's blank bubble baseline instead of a hand-tuned `global_thr` surplus.

21-sheet validation event:

```text
Weak multi full-select fallback: field 'q10' -> 'ABCD' (max_mean=146.77, max_allowed_mean=150.85, spread=7.57)
```

30-sheet validation event with adaptive page blank baseline:

```text
Weak multi full-select fallback: field 'q11' -> 'ABCD' (max_mean=143.55, page_blank_baseline=223.81, delta_from_page_blank=80.26, spread=8.12)
```

Validation command:

```bash
python main.py -i inputs -o outputs_inputs_21_full_select_guarded
python main.py -i inputs -o outputs_inputs_30_adaptive_full_select
```

Validation result for 30-sheet scan after the final threshold setting:

```text
rows 30
id_blank_cells 0
id_blank_rows 0
q_blank_cells 0
any_blank_rows 0
MX-M3658N_20260731_153802_015.png q11=ABCD
```

Compared with the run before adaptive full-select recovery, the answer columns changed only here:

```text
MX-M3658N_20260731_153802_015.png q11 '' -> 'ABCD'
```

Earlier 21-sheet validation result:

```text
rows 21
id_blank_cells 0
id_blank_rows 0
q_blank_cells 0
any_blank_rows 0
MX-M3658N_20260731_123655_007.png q10=ABCD
```

Compared with the feature-alignment-only run, the answer columns changed only here. Compared with the earlier fixed-label guarded run, the answer columns are identical:

```text
MX-M3658N_20260731_123655_007.png q10 '' -> 'ABCD'
```


## Remaining Parameter Adaptation Risks

The current 56-sheet review should be treated as an observation pass for the remaining fixed thresholds. The template-level `multiSelect` flag has removed the earlier fixed-label dependency, and the full-select fallback now uses a page-level blank baseline instead of the old `global_thr + surplus` rule. However, a few conservative thresholds are still absolute or semi-absolute and may need future adaptation if scans come from a different device, paper shade, fill darkness, or answer density.

Current remaining risks:

- `full_select_max_mean`: absolute darkness guard for all-selected multi-select rows. It prevents blank rows from being filled accidentally, but can be too strict for lighter scans or too loose for darker backgrounds.
- `full_select_max_spread`: fixed uniformity guard for all-selected rows. It is useful because true full-select rows should have similar option means, but unusual pen pressure or scanner noise can widen the spread.
- `full_select_min_delta_from_blank`: page-relative and more adaptive than `global_thr + surplus`, but still uses a fixed required gap from the estimated blank baseline.
- The page blank baseline currently uses the lightest 25% of all bubbles. This works for the current sheets, but pages with very high answer density may have fewer true blank bubbles and can bias the baseline darker.
- `weak_mark_params.max_mean` and `weak_multi_mark_params.max_mean`: absolute upper bounds for weak single-choice and weak multi-choice recovery. These are intentionally conservative, but remain scan-dependent.
- `weak_mark_params.min_gap` and `weak_multi_mark_params.min_delta_from_blank`: fixed contrast requirements. They reduce false positives, but can still miss very light marks.

Recommended next optimization after the 56-sheet review:

1. Keep the current conservative configuration as the verified baseline.
2. Add reporting for every fallback trigger, grouped by fallback type and field label, so future batches can be audited quickly.
3. Consider making absolute `max_mean` guards optional secondary caps, while the primary decision uses page-local or question-local contrast from the blank baseline.
4. Expose the blank-baseline quantile as configuration, for example `blank_baseline_quantile`, and validate whether 75% remains stable across higher answer-density sheets.
5. Add a per-page fallback trigger cap or warning threshold. This would not block valid recovery, but would make suspicious pages visible before results are trusted.
6. Use the current 56-sheet run to decide whether further adaptation is actually needed. If no unexpected fallback triggers or blank fields appear, avoid broadening thresholds prematurely.


## 56-sheet Current-parameter Review

Command:

```bash
python main.py -i inputs -o outputs_inputs_56_current_params
```

Result CSV:

```text
outputs_inputs_56_current_params/Results/Results_03PM.csv
```

Summary:

```text
rows 56
id_blank_cells 1
q_blank_cells 0
blank_cells 1
blank_rows 1
MX-M3658N_20260731_160125_005.png id8
```

Fallback trigger summary from `recognize_56_current_params.log`:

```text
Weak multi full-select fallback: 2
Weak mark fallback: 0
Weak multi-mark fallback: 0
```

The two full-select fallback events are the expected multi-select all-filled recoveries:

```text
Weak multi full-select fallback: field 'q10'
Weak multi full-select fallback: field 'q11'
```

The only remaining blank cell is an identifier digit, not an answer question. For `MX-M3658N_20260731_160125_005.png id8`, the configured ROI statistics were:

```text
id8 means: 0:221.51, 1:222.30, 2:223.16, 3:220.67, 4:221.69, 5:217.08, 6:191.56, 7:218.32, 8:218.43, 9:218.61
darkest candidate: 6
second-darkest gap: 25.52
```

This suggests the last identifier digit may be a weak mark around `6`, but identifier fallback was not enabled in that run. The current weak single-choice fallback is intentionally limited to `QTYPE_MCQ4` answer fields, so identifier recovery is handled as a separate, stricter feature.

## Weak Identifier Fallback

The identifier fallback is separate from answer weak-mark recovery because a false positive changes the student's identity. It only runs for identifier fields configured as `QTYPE_INT`, and only when the normal recognition result for that digit is blank.

Additional config fields:

```json
"weak_identifier_params": {
  "enabled": true,
  "labels": [],
  "exclude_labels": [],
  "min_gap": 20,
  "min_delta_from_blank": 25,
  "max_mean": 205,
  "supported_field_types": ["QTYPE_INT"]
}
```

Guard conditions:

- `supported_field_types` must include the field block type, currently `QTYPE_INT`.
- `labels` can restrict recovery to known identifier labels. Empty `labels` means all `QTYPE_INT` identifier labels are eligible.
- The original recognition for that digit must be blank.
- The darkest candidate must be at least `min_gap` darker than the second-darkest candidate.
- The darkest candidate must be at least `min_delta_from_blank` darker than the local blank baseline estimated from the lighter half of that digit's 0-9 options.
- The darkest candidate must not exceed `max_mean`, which remains a conservative secondary absolute cap.

Validation on the 56-sheet set after enabling `weak_identifier_params`:

```bash
python main.py -i inputs -o outputs_inputs_56_weak_identifier
```

```text
rows 56
id_blank_cells 0
q_blank_cells 0
blank_cells 0
blank_rows 0
MX-M3658N_20260731_160125_005.png id=25803716
```

Compared with the pre-identifier-fallback 56-sheet run, the recognized output changed only here:

```text
MX-M3658N_20260731_160125_005.png id8 '' -> '6'
```

Fallback trigger summary from `weak_identifier_56.log`:

```text
Weak identifier fallback: 1, field id8
Weak multi full-select fallback: 2, fields q10 and q11
Weak mark fallback: 0
Weak multi-mark fallback: 0
```
