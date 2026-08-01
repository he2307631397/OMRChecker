# Single Choice Auto Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build default-off single-choice conflict auto recovery that resolves high-confidence multi-detected single-choice fields to the strongest candidate and marks medium-confidence recoveries for manual review.

**Architecture:** Reuse the existing `get_single_choice_conflict_confidence()` and `append_single_choice_conflict_review()` paths. Add two config thresholds under `weak_mark_params`: `conflict_auto_resolve_min_confidence` default `0.8` and `conflict_review_min_confidence` default `0.65`. When `resolve_single_choice_conflicts=true`, `resolve_single_choice_conflict()` will return the darkest candidate for confidence >= 0.65, with status `RESOLVED_CANDIDATE` for >= 0.8 and `NEEDS_REVIEW` for 0.65-0.8; lower confidence remains blank with `LOW_CONFIDENCE`.

**Tech Stack:** Python, DotMap config, JSON schema validation, pytest.

---

### Task 1: Add TDD coverage for confidence-based conflict resolution

**Files:**
- Modify: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Add tests before production code**

Append these tests after the existing single-choice conflict tests in `tests/test_weak_fill_features.py`:

```python
def test_single_choice_conflict_high_confidence_auto_resolves_without_review_status():
    ops = make_ops(
        resolve_single_choice_conflicts=True,
        conflict_auto_resolve_min_confidence=0.8,
        conflict_review_min_confidence=0.65,
    )
    field = FakeFieldBlock(multi_select=False)
    bubbles = make_bubbles()
    detected = [bubbles[0], bubbles[1], bubbles[2], bubbles[3]]

    resolved = ops.resolve_single_choice_conflict(
        field,
        bubbles,
        [196.584, 188.276, 163.636, 189.782],
        detected,
    )

    assert [bubble.field_value for bubble in resolved] == ["C"]
    assert ops.last_weak_fill_reviews[-1]["review_type"] == "SINGLE_CHOICE_CONFLICT_REVIEW"
    assert ops.last_weak_fill_reviews[-1]["candidate"] == "C"
    assert ops.last_weak_fill_reviews[-1]["status"] == "RESOLVED_CANDIDATE"
    assert ops.last_weak_fill_reviews[-1]["confidence"] >= 0.8


def test_single_choice_conflict_medium_confidence_auto_resolves_with_review_status():
    ops = make_ops(
        resolve_single_choice_conflicts=True,
        conflict_auto_resolve_min_confidence=0.8,
        conflict_review_min_confidence=0.65,
    )
    field = FakeFieldBlock(multi_select=False)
    bubbles = make_bubbles()
    detected = [bubbles[0], bubbles[1], bubbles[2]]

    resolved = ops.resolve_single_choice_conflict(
        field,
        bubbles,
        [178.0, 190.0, 199.0, 220.0],
        detected,
    )

    assert [bubble.field_value for bubble in resolved] == ["A"]
    assert ops.last_weak_fill_reviews[-1]["candidate"] == "A"
    assert ops.last_weak_fill_reviews[-1]["status"] == "NEEDS_REVIEW"
    assert 0.65 <= ops.last_weak_fill_reviews[-1]["confidence"] < 0.8


def test_single_choice_conflict_below_review_confidence_blanks_candidate():
    ops = make_ops(
        resolve_single_choice_conflicts=True,
        conflict_auto_resolve_min_confidence=0.8,
        conflict_review_min_confidence=0.65,
    )
    field = FakeFieldBlock(multi_select=False)
    bubbles = make_bubbles()
    detected = [bubbles[0], bubbles[1], bubbles[2]]

    resolved = ops.resolve_single_choice_conflict(
        field,
        bubbles,
        [190.0, 194.0, 198.0, 220.0],
        detected,
    )

    assert resolved == []
    assert ops.last_weak_fill_reviews[-1]["candidate"] == "A"
    assert ops.last_weak_fill_reviews[-1]["status"] == "LOW_CONFIDENCE"
    assert ops.last_weak_fill_reviews[-1]["confidence"] < 0.65
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_weak_fill_features.py::test_single_choice_conflict_high_confidence_auto_resolves_without_review_status tests/test_weak_fill_features.py::test_single_choice_conflict_medium_confidence_auto_resolves_with_review_status tests/test_weak_fill_features.py::test_single_choice_conflict_below_review_confidence_blanks_candidate -q
```

Expected: FAIL because `NEEDS_REVIEW` behavior and the confidence threshold config are not implemented yet.

### Task 2: Add confidence threshold configuration

**Files:**
- Modify: `src/defaults/config.py`
- Modify: `src/schemas/config_schema.py`
- Modify: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Update default config**

Add under `weak_mark_params`, immediately after `conflict_min_delta_from_blank`:

```python
"conflict_auto_resolve_min_confidence": 0.8,
"conflict_review_min_confidence": 0.65,
```

- [ ] **Step 2: Update JSON schema**

Add under the `weak_mark_params` schema properties, immediately after `conflict_min_delta_from_blank`:

```python
"conflict_auto_resolve_min_confidence": {
    "type": "number",
    "minimum": 0,
    "maximum": 1,
},
"conflict_review_min_confidence": {
    "type": "number",
    "minimum": 0,
    "maximum": 1,
},
```

- [ ] **Step 3: Update test helper defaults**

Add to `make_ops()` params immediately after `conflict_min_delta_from_blank`:

```python
"conflict_auto_resolve_min_confidence": 0.8,
"conflict_review_min_confidence": 0.65,
```

- [ ] **Step 4: Run config-focused tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_weak_fill_features.py -q
```

Expected: existing behavior may still fail until Task 3 is implemented, but there should be no schema or missing-key errors.

### Task 3: Implement confidence-based resolution logic

**Files:**
- Modify: `src/core.py`

- [ ] **Step 1: Replace threshold-only branch**

In `resolve_single_choice_conflict()`, replace the branch that currently checks `gap >= weak_mark_params.conflict_min_gap or delta_from_blank >= weak_mark_params.conflict_min_delta_from_blank` with confidence-based status selection:

```python
confidence = self.get_single_choice_conflict_confidence(diagnostics)
auto_resolve_min_confidence = getattr(
    weak_mark_params, "conflict_auto_resolve_min_confidence", 0.8
)
review_min_confidence = getattr(
    weak_mark_params, "conflict_review_min_confidence", 0.65
)

if confidence >= auto_resolve_min_confidence:
    status = "RESOLVED_CANDIDATE"
elif confidence >= review_min_confidence:
    status = "NEEDS_REVIEW"
else:
    status = "LOW_CONFIDENCE"

if status in {"RESOLVED_CANDIDATE", "NEEDS_REVIEW"}:
    logger.warning(
        f"Single-choice conflict resolved: field '{field_label}' "
        f"{''.join(b.field_value for b in detected_bubbles)} -> "
        f"'{darkest_bubble.field_value}' "
        f"status={status} confidence={confidence:.3f} "
        f"(darkest_mean={diagnostics['darkest_mean']:.2f}, "
        f"second_darkest_mean={diagnostics['second_darkest_mean']:.2f}, "
        f"gap={gap:.2f}, blank_baseline={diagnostics['blank_baseline']:.2f}, "
        f"delta={delta_from_blank:.2f})"
    )
    self.append_single_choice_conflict_review(
        field_label,
        "".join(b.field_value for b in detected_bubbles),
        darkest_bubble.field_value,
        diagnostics,
        status,
    )
    return [darkest_bubble]

logger.warning(
    f"Single-choice conflict unresolved: field '{field_label}' "
    f"{''.join(b.field_value for b in detected_bubbles)} -> blank "
    f"status={status} confidence={confidence:.3f} "
    f"(darkest_mean={diagnostics['darkest_mean']:.2f}, "
    f"second_darkest_mean={diagnostics['second_darkest_mean']:.2f}, "
    f"gap={gap:.2f}, blank_baseline={diagnostics['blank_baseline']:.2f}, "
    f"delta={delta_from_blank:.2f})"
)
self.append_single_choice_conflict_review(
    field_label,
    "".join(b.field_value for b in detected_bubbles),
    darkest_bubble.field_value,
    diagnostics,
    status,
)
return []
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_weak_fill_features.py::test_single_choice_conflict_high_confidence_auto_resolves_without_review_status tests/test_weak_fill_features.py::test_single_choice_conflict_medium_confidence_auto_resolves_with_review_status tests/test_weak_fill_features.py::test_single_choice_conflict_below_review_confidence_blanks_candidate -q
```

Expected: PASS.

### Task 4: Full verification and commit

**Files:**
- Verify: `src/core.py`
- Verify: `src/defaults/config.py`
- Verify: `src/schemas/config_schema.py`
- Verify: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Run target pytest suite**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run four-scenario regression with default config**

Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_omr_regression.py | tee jcode_regression_summary_after_single_choice_auto_recovery.txt
```

Expected: default config keeps `resolve_single_choice_conflicts=false`, so main Results metrics remain unchanged from the prior baseline.

- [ ] **Step 3: Commit only this feature's files**

Run:

```bash
git add docs/superpowers/plans/2026-08-01-single-choice-auto-recovery.md src/core.py src/defaults/config.py src/schemas/config_schema.py tests/test_weak_fill_features.py
git commit -m "feat: add confidence-based single-choice recovery"
```

Expected: commit succeeds and existing unrelated dirty files remain unstaged.
