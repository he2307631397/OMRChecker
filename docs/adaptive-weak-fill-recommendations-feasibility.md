# Adaptive OMR Weak-fill Recommendations Feasibility Review

## Source

Reviewed document:

```text
docs/Adaptive_OMR_Weak_Fill_Optimization_Recommendations.md
```

Related current design document:

```text
docs/adaptive-weak-fill-design.md
```

Current branch:

```text
weak-fill-enhancement
```

## Overall Conclusion

The recommendations are feasible and align well with the current adaptive weak-fill design.

They do not require overturning the existing design. Instead, they refine the design from a mean/gap/delta fallback into a more robust feature-based confidence model.

The best near-term adoption path is:

```text
P0: local/page blank model + density score + z-score + audit logs
P1: multi-threshold binary analysis + identifier sequence checks + review CSV
P2: shape score and machine-learning confidence model
```

This sequence is compatible with the current project constraints:

- Keep the normal recognition path unchanged.
- Only run fallback for blank fields.
- Do not use enhanced images as the main recognition input.
- Keep identifier recovery more conservative than answer recovery.
- Preserve existing multi-select and full-select behavior.
- Validate against the 10-sheet weak-fill set and the 56-sheet normal-fill baseline before merging.

## Fit With Current Code Structure

The current code already has separate fallback entry points:

- `get_weak_marked_bubble()` for weak single-choice fallback.
- `get_weak_identifier_bubble()` for weak identifier fallback.
- `get_weak_multi_marked_bubbles()` for weak multi-select fallback.
- `get_weak_multi_full_select_bubbles()` for weak all-option multi-select fallback.

This separation is helpful. The recommendation to introduce field-type policies can be implemented without rewriting the main OMR path.

A practical implementation should add shared diagnostic helpers used by these fallback functions rather than duplicating score logic in each function.

Suggested helper concepts:

```text
BubbleDiagnostics
  label
  mean
  dark_pixel_ratio
  threshold_occupancy_by_level

FieldDiagnostics
  field_label
  field_type
  local_blank_mean
  local_blank_std
  candidates
  darkest_candidate
  second_darkest_candidate
  gap
  delta_from_local_blank
  z_score

PageBlankModel
  blank_mean
  blank_std
  blank_density_mean
  blank_density_std
```

## Recommendation-by-Recommendation Assessment

### 1. MarkScore

Status: feasible, but should be introduced as an internal diagnostic score first.

The idea is correct because weak fill is not only about the darkest mean. A filled bubble often has local stroke structure, while scan noise or a printed border can also lower the mean.

Recommended approach:

- Do not immediately create a complex weighted formula.
- Start by logging components separately.
- Use simple conservative rules for the first implementation.
- After enough test data, combine components into a formal `MarkScore`.

Risk:

- A weighted score can become another hand-tuned threshold system if introduced too early.
- It should not replace explicit safety checks for identifiers.

Feasibility: high.

Priority: P0 as logged components, P1/P2 as a formal score.

### 2. DensityScore

Status: strongly feasible and recommended for first implementation.

`dark_pixel_ratio` is useful because weak fills may contain partial pencil or pen strokes that do not change the full ROI mean enough. Density can detect whether a meaningful portion of the bubble area is darker than local blank background.

Implementation detail:

Use local/page adaptive thresholds rather than fixed absolute values only.

Better than:

```text
pixel < 200
```

Prefer:

```text
pixel < local_blank_mean - k
pixel < page_blank_mean - k
```

or multi-level occupancy relative to blank baseline.

Risk:

- Printed bubble borders can increase density if the ROI includes too much border.
- Dust, compression artifacts, or scan shadows can produce scattered dark pixels.

Mitigation:

- Compute density inside the same bubble ROI currently used by OMR, and if needed use a slightly eroded inner ROI to reduce border influence.
- Compare candidate density against other candidates in the same field.
- Use density as support, not as a single sufficient condition for identifiers.

Feasibility: high.

Priority: P0.

### 3. ShapeScore

Status: feasible but not first priority.

Connected-component area, ROI coverage, and compactness can help distinguish real fill from dust or line artifacts. However, it is more sensitive to ROI geometry, binarization thresholds, printed borders, and scan resolution.

For the current weak-fill 10-sheet problem, mean/gap/delta already show usable signal for answer blanks, so density and blank distribution should be tried before shape analysis.

Risk:

- More code complexity.
- Higher chance of overfitting to current template dimensions.
- Needs careful ROI erosion or border masking.

Feasibility: medium.

Priority: P2 unless density still leaves ambiguous cases.

### 4. DistributionScore

Status: feasible and already aligned with the adaptive design.

Comparing one candidate against the other candidates in the same field and the page-level blank distribution is important. It is safer than fixed global thresholds because it adapts to scanner brightness and paper variation.

Recommended first implementation:

- Keep local field comparison: darkest versus lighter candidates.
- Add page blank mean/std.
- Add candidate z-score versus page blank distribution.
- Require stronger z-score or local delta for identifiers than for answer fields.

Risk:

- Page blank distribution can be polluted if many fields are actually filled.
- Multi-select fields can distort page distributions because several options per field may be marked.

Mitigation:

- Build blank model from the lighter percentile of all bubble means, not all bubbles.
- Consider excluding obvious marked candidates and multi-select full-select rows from the blank model.
- Start with robust statistics such as median and MAD or percentile bands.

Feasibility: high.

Priority: P0.

### 5. Page Blank Distribution

Status: strongly feasible and recommended.

This should be the backbone of the adaptive fallback. It gives the system a page-specific understanding of blank bubble appearance.

Practical model:

```text
page_blank_mean = median of high-lightness bubble means, or percentile around 70-90%
page_blank_std = robust std or MAD from the same group
page_blank_density = density distribution for likely blank bubbles
```

Use cases:

- Identify weak-fill pages.
- Compute z-score for blank-field candidates.
- Guard against absolute threshold overfitting.
- Trigger warnings when too many fallbacks are needed.

Risk:

- Bad alignment or page crop errors can corrupt ROI statistics.
- Very dark scans can make blank distribution less separated from marks.

Mitigation:

- Log page model values.
- If page model looks abnormal, keep fallback conservative and flag review.

Feasibility: high.

Priority: P0.

### 6. Multi-threshold Binary Analysis

Status: feasible and useful as a second-stage confidence feature.

The recommendation to prefer multi-threshold occupancy before CLAHE is sound. It is simpler, auditable, and less likely to alter the meaning of the image.

Implementation approach:

For each candidate ROI, compute occupancy ratios at thresholds derived from local blank baseline:

```text
thresholds = [blank_mean - 10, blank_mean - 20, blank_mean - 30, blank_mean - 40]
```

or combine with absolute thresholds as diagnostics only.

A true fill should generally maintain higher occupancy than other candidates across multiple thresholds.

Risk:

- Absolute thresholds like 180/200/220/240 may not generalize across scanners.
- If the ROI includes printed border, occupancy can be inflated.

Mitigation:

- Prefer relative thresholds.
- Use inner ROI or border-aware masks if necessary.
- Compare occupancy pattern against sibling candidates.

Feasibility: high.

Priority: P1, after density and blank model.

### 7. RecognitionPolicy by Field Type

Status: feasible and necessary.

This matches the current project need very well. Answer fallback and identifier fallback have different risk profiles.

Recommended policies:

```text
Single-choice answer:
  fallback allowed on blank fields with medium-high confidence
  one recovered candidate only

Identifier digit:
  fallback allowed only with high confidence
  stronger local/page evidence required
  log and optionally review all recovered digits

Multi-select:
  independent logic only
  do not reuse single-choice scoring
  keep template-level multiSelect support
```

Risk:

- If policies are over-configured, the system can regress into scene-specific parameter tuning.

Mitigation:

- Encode policies as small fixed risk classes, not per-batch tuning profiles.

Feasibility: high.

Priority: P0.

### 8. Identifier Sequence Model

Status: conceptually valuable, but limited by available business rules.

The sequence model is useful for review and risk control. However, it should not infer a digit merely because it makes the identifier look more plausible unless there is a known checksum, roster list, or database of valid identifiers.

Safe near-term uses:

- Count how many identifier positions were recovered by fallback.
- Warn if several adjacent positions are blank or weak.
- Require stricter confidence if many identifier digits are weak on the same sheet.
- Export recovered identifier digits to review CSV.

Unsafe unless external validation exists:

- Guessing a digit because it fits a likely ID pattern.
- Replacing a weak but recognized digit based on neighboring digits.

Feasibility: medium-high for audit and gating, low for automatic correction without external roster/checksum.

Priority: P1.

### 9. Adaptive Review CSV

Status: strongly feasible and recommended.

This is especially important because identifier fallback affects the whole sheet.

Suggested output:

```text
adaptive_review.csv
sheet, field, field_type, normal_result, adaptive_result, confidence, action, reason, darkest_mean, second_mean, gap, local_blank_mean, page_blank_mean, z_score, density, fallback_family
```

Actions:

```text
recovered
kept_blank_low_confidence
warning_too_many_fallbacks
```

Risk:

- Adds output file management work.
- Needs consistency with current output directory layout.

Feasibility: high.

Priority: P1, or P0 if implementation time allows.

### 10. Machine Learning Confidence Model

Status: not recommended for the current stage.

It may be useful later, but the current dataset is too small and the project still needs transparent rules to protect the normal-fill baseline.

Preconditions before ML:

- Accumulated review CSV data.
- Labeled recovered/false-positive/true-blank examples.
- Diverse scanners and fill strengths.
- Stable feature extraction pipeline.

Feasibility: future only.

Priority: P2.

## Specific Impact on Current 10-sheet Weak-fill Set

The document's analysis of q5/q3/q6 is reasonable.

Current known answer blanks:

```text
001 q5: darkest=A mean=209.01 gap=25.64 delta_from_blank=45.99
008 q3: darkest=A mean=205.15 gap=10.61 delta_from_blank=39.23
009 q6: darkest=D mean=158.74 gap=49.36 delta_from_blank=75.93
```

Expected behavior:

- `009 q6` should be recovered by local delta and gap alone.
- `001 q5` should likely be recovered by local delta plus density.
- `008 q3` is the most important test for density and page distribution because gap is weaker.

This supports the recommendation that local mean/gap/delta is necessary but not sufficient.

Identifier blanks are more sensitive. The first implementation should try to reduce them, but it should prefer leaving low-confidence identifier cells blank over guessing.

## Recommended Implementation Order for This Branch

### Step 1: Stabilize the current code state

There is currently an uncommitted `src/core.py` draft change from an earlier attempt. Before implementing the recommendations, decide whether to keep, revise, or revert that draft.

Recommended action:

- Do not commit it as-is.
- Rework it into the diagnostic helper approach.

### Step 2: Add shared diagnostics

Implement reusable helpers for:

- candidate mean
- local blank baseline
- local blank std
- gap
- local delta
- page blank mean/std
- density ratio using relative threshold

### Step 3: Single-choice adaptive fallback

Apply only when:

- normal result is blank
- field type is single-choice
- field is not `multiSelect`

Use:

- local delta
- gap
- page z-score
- density support

Goal for weak-fill 10-sheet set:

```text
q_blank_cells: 3 -> 0
```

### Step 4: Identifier adaptive fallback

Apply only when:

- normal result is blank
- field type is identifier digit
- confidence is high

Use stricter thresholds than answer fields and log every recovery.

Goal for weak-fill 10-sheet set:

```text
id_blank_cells: 12 -> lower, ideally 0 if confidence supports it
```

But preserving correctness is more important than forcing zero blanks.

### Step 5: Audit output

At minimum, keep log diagnostics. Prefer adding `adaptive_review.csv` once basic recovery works.

### Step 6: Regression tests

Run weak-fill 10-sheet test first, then restore and run normal-fill 56-sheet regression.

Merge only if:

- weak-fill blanks improve materially
- normal 56-sheet baseline remains clean
- no unexpected answer differences appear
- fallback logs are explainable

## Risk Summary

| Recommendation | Feasibility | Risk | Suggested Phase |
| --- | --- | --- | --- |
| DensityScore | High | Medium if border/noise is included | P0 |
| Page Blank Distribution | High | Medium if page alignment is bad | P0 |
| z-score | High | Low-medium depending on blank model quality | P0 |
| Field RecognitionPolicy | High | Low | P0 |
| Multi-threshold analysis | High | Medium if absolute thresholds are used | P1 |
| Identifier sequence check | Medium-high | Medium if used to infer digits | P1 |
| Review CSV | High | Low | P1 |
| ShapeScore | Medium | Medium-high complexity | P2 |
| ML confidence model | Future | High without labeled data | P2 |

## Final Recommendation

Adopt the document's recommendations, but do it incrementally.

The first coding target should be:

```text
page blank distribution
+ local field diagnostics
+ density score
+ z-score
+ field-type-specific conservative decisions
```

Do not start with CLAHE, ShapeScore, or ML. Do not use identifier sequence context to guess digits unless there is a trusted external validation source.

This is the safest path to improve the current 10-sheet weak-fill case while protecting the already verified 56-sheet normal-fill baseline.
