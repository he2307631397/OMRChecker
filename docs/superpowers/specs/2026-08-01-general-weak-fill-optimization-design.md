# General Weak-fill OMR Optimization Design

## Purpose

Improve weak-fill answer sheet recognition without tuning for the specific files in `docs/assets`.
The provided assets are validation scenarios, not parameters to fit.

The optimization must preserve existing achievements:

- Normal-fill recognition remains stable.
- Overflow marking behavior does not regress.
- Underfilled sheet behavior does not gain unsafe false positives.
- Multi-select and identifier fallbacks keep their existing safety boundaries.

## Non-goals

- No hard-coded file names, batch IDs, answer keys, coordinates, or per-sample exceptions.
- No broad lowering of the main thresholding path.
- No replacement of the original page image for normal recognition.
- No guessing for low-confidence single-choice conflicts.
- No training or deploying a neural model in this stage.

## Current Baseline

Command pattern:

```bash
python main.py -i <scenario_input_dir> -o <scenario_output_dir>
```

The current four-scenario baseline using copied `inputs` config and `docs/assets` PDFs is:

| Scenario | Rows | ID blanks | Answer blanks | Blank rows | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Weak fill | 10 | 1 | 3 | 4 | Remaining blanks: `001 q5`, `004 id7`, `008 q3`, `009 q6` |
| Normal fill | 56 | 0 | 0 | 0 | Must stay 0 blank cells |
| Underfilled | 4 | 8 | 0 | 1 | One intentionally incomplete ID row remains blank |
| Overflow | 4 | 0 | 0 | 0 | Must not introduce extra blanks or unsafe fallback |

Observed weak-fill failure mode:

- Remaining answer blanks have high page-level darkness evidence, but weak local separation.
- Current single-choice fallback rejects them via local delta/gap guards.
- This means simple threshold lowering is unsafe and insufficient.

## Design Principle

Use a general confidence model built from reusable bubble features.
The normal recognition path remains the source of truth.
Fallback runs only after normal recognition returns blank for a field.

The model should answer:

> Is exactly one candidate sufficiently mark-like compared with the page, the local field, and its own ROI structure?

It should not answer:

> Does this candidate resemble one of the known failing samples?

## BubbleFeature

For every bubble ROI, compute a general feature object:

```text
BubbleFeature:
  field_label
  field_value
  field_type
  multi_select
  mean
  local_delta
  page_delta
  candidate_gap
  dark_ratio
  center_density
  edge_density
  center_edge_ratio
  page_z_score
  rank_in_field
```

Feature definitions:

- `mean`: average grayscale in the existing bubble ROI.
- `local_delta`: local blank baseline minus candidate mean.
- `page_delta`: page blank baseline minus candidate mean.
- `candidate_gap`: second darkest candidate mean minus darkest mean.
- `dark_ratio`: fraction of pixels darker than a page or local adaptive threshold.
- `center_density`: dark-pixel density in the central ROI.
- `edge_density`: dark-pixel density in an outer ring or border area.
- `center_edge_ratio`: helps separate fill marks from printed borders or erasure edge noise.
- `page_z_score`: candidate darkness relative to page blank distribution.
- `rank_in_field`: candidate ordering inside the current field.

These features are general and reusable for weak fill, erasure traces, and future review UI.

## Page and Field Diagnostics

Before fallback, compute diagnostics:

```text
PageDiagnostics:
  page_blank_mean
  page_blank_std
  page_weak_fill_likelihood
  fallback_candidate_count

FieldDiagnostics:
  darkest_candidate
  second_darkest_candidate
  local_blank_baseline
  local_gap
  local_delta
  field_candidate_count
```

`page_weak_fill_likelihood` is not a mode switch. It only provides supporting context.
A candidate still needs field and ROI evidence.

## Single-choice Weak-fill Fallback

Applies only when all conditions are true:

1. Normal recognition returned blank.
2. Field type is `QTYPE_MCQ4`.
3. Template field is not `multiSelect`.
4. Field label is not excluded by configuration.
5. Exactly one candidate has the highest confidence.
6. Confidence is above the accepted threshold.
7. Ambiguity score is below the review threshold.

Confidence uses multiple general signals:

```text
mark_confidence = weighted evidence from:
  page_delta
  page_z_score
  dark_ratio
  center_density
  center_edge_ratio
  local_delta
  candidate_gap
```

No single feature should be enough by itself unless it is extremely strong and the ambiguity score is low.
This prevents a broad threshold decrease from turning noise into answers.

## Identifier Fallback

Identifier fallback remains stricter than answer fallback.
This stage may reuse `BubbleFeature`. It should not loosen identifier behavior unless the same scoring model has specific
high-confidence support.

Rules:

- Applies only to blank identifier fields.
- Requires stronger local separation than single-choice answer fallback.
- Requires strong ROI density support.
- Logs every accepted and rejected candidate.

## Multi-select Behavior

Multi-select logic remains separate.
Do not use single-choice scoring for multi-select fields.
Existing weak multi-mark and full-select fallback must continue to support legal `ABCD` responses.

## Review and Safety States

Candidate status should be explainable:

```text
EMPTY
MARK
WEAK_MARK
REVIEW
ERASE_TRACE (future stage)
```

For this stage:

- `MARK`: normal recognition result.
- `WEAK_MARK`: accepted fallback with high confidence.
- `REVIEW`: candidate has evidence but not enough to auto-fill.
- `EMPTY`: no sufficient evidence.

If code output cannot yet carry structured review states, logs must record the equivalent status.

## Regression Gates

Every implementation attempt must run all four scenarios:

| Scenario | Gate |
| --- | --- |
| Normal fill 56 | 56 rows, 0 ID blanks, 0 answer blanks, no broad fallback increase |
| Weak fill 10 | Blank cells should decrease from current 4 without introducing conflicts |
| Underfilled 4 | Do not fill intentionally blank ID row by weak fallback |
| Overflow 4 | Do not add unsafe fallback or extra blank regressions |

Additional guardrails:

- Count fallback events by family.
- Compare CSV outputs against the pre-change baseline.
- Flag any changed normal-fill answers for manual review.
- Flag any new underfilled ID recovery as unsafe unless separately approved.

## Implementation Shape

Recommended minimal code structure:

1. Add a small `BubbleFeature` helper in `src/core.py` or a new focused module if extraction keeps `core.py` readable.
2. Refactor existing diagnostics to populate `BubbleFeature` without changing normal thresholding.
3. Add a single-choice confidence function that returns status, score, reason, and candidate.
4. Call the confidence function only inside the existing weak-mark fallback path.
5. Extend logs to include feature values and rejection reasons.
6. Add a scenario runner script for repeatable regression statistics.

## Acceptance Criteria

The optimization is acceptable only if:

1. It contains no sample-specific conditions.
2. Main threshold recognition is unchanged.
3. Fallback remains blank-only.
4. Normal-fill 56 remains at 0 blanks.
5. Overflow scenario does not regress.
6. Underfilled scenario does not auto-fill the intentionally blank ID row.
7. Weak-fill blank count decreases or review diagnostics become more actionable.
8. Logs explain every fallback and every near-miss review candidate.

## Open Implementation Decision

The exact confidence weights should start conservative and feature-based.
They must be expressed as general guardrails, not fitted constants for the supplied batch.
If a candidate needs sample-specific tuning to pass, it should remain `REVIEW` rather than auto-filled.
