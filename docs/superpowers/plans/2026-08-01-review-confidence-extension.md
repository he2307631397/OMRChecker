# Review Confidence Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the auxiliary review CSV to include weak marks, single-choice conflicts, and ID candidates with confidence, while leaving `Results_*.csv` unchanged.

**Architecture:** Keep the main OMR thresholding flow stable. Add per-page review records inside `ImageInstanceOps`, write them through the existing `append_weak_fill_review_rows` output hook, and gate single-choice conflict review by template `multi_select` so true multi-select questions are not affected.

**Tech Stack:** Python, OpenCV/Numpy diagnostics already in `src/core.py`, pandas CSV output in `src/entry.py` and `src/utils/file.py`, pytest regression tests.

---

## File Structure

- Modify `src/core.py`
  - Add reusable review record helpers.
  - Add `SINGLE_CHOICE_CONFLICT_REVIEW` records when a non-multi-select field has multiple detected bubbles.
  - Add `ID_REVIEW` records from weak identifier candidate evaluation.
  - Keep answer mutation behavior unchanged in this phase.
- Modify `src/utils/file.py`
  - Extend `WeakFillReview.csv` header with review type and original value fields.
- Modify `src/entry.py`
  - Extend row writer to handle the new fields while retaining existing weak mark rows.
- Modify `tests/test_weak_fill_features.py`
  - Add TDD tests for conflict review, multi-select exclusion, ID review, CSV header, and CSV writer.
- Create `docs/weak-fill-optimization/regression-summaries/2026-08-01-review-confidence-extension.md`
  - Record validation commands and four-scenario metrics.

---

### Task 1: Extend auxiliary CSV schema and writer

**Files:**
- Modify: `src/utils/file.py`
- Modify: `src/entry.py`
- Test: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Write the failing header test**

Append this test to `tests/test_weak_fill_features.py` or update the existing header test so it expects the new fields:

```python
def test_review_csv_header_includes_review_type_and_original_value(tmp_path):
    from types import SimpleNamespace

    from src.utils.file import setup_outputs_for_template

    paths = SimpleNamespace(
        results_dir=tmp_path / "Results",
        manual_dir=tmp_path / "Manual",
    )
    paths.results_dir.mkdir()
    paths.manual_dir.mkdir()
    template = SimpleNamespace(output_columns=["q1", "q2"])

    setup_outputs_for_template(paths, template)

    header = (
        (tmp_path / "Results" / "WeakFillReview.csv")
        .read_text()
        .splitlines()[0]
    )
    assert header.startswith(
        '"file_id","input_path","output_path","review_type","field",'
        '"original_value","candidate","confidence","status"'
    )
```

- [ ] **Step 2: Write the failing writer test**

Add this test to `tests/test_weak_fill_features.py`:

```python
def test_append_review_rows_writes_review_type_and_original_value(tmp_path):
    from types import SimpleNamespace

    from src.entry import append_weak_fill_review_rows

    csv_path = tmp_path / "WeakFillReview.csv"
    review = {
        "review_type": "SINGLE_CHOICE_CONFLICT_REVIEW",
        "field": "q1",
        "original_value": "ABCD",
        "candidate": "C",
        "confidence": 0.82,
        "status": "RESOLVED_CANDIDATE",
        "reason": "single_choice_conflict",
        "evidence": "gap,delta_from_blank,center_density",
        "score": 4.2,
        "legacy_rejection": "",
        "ambiguity": 0.08,
        "density_gap": 0.25,
        "center_density": 0.62,
        "center_edge_ratio": 6.0,
        "threshold_vote_ratio": 0.75,
        "multiscale_stability": 1.0,
    }
    outputs = SimpleNamespace(files_obj={"WeakFillReview": str(csv_path)})

    append_weak_fill_review_rows(
        "sheet.png",
        "/in/sheet.png",
        "/out/sheet.png",
        [review],
        outputs,
    )

    assert csv_path.read_text().splitlines() == [
        '"sheet.png","/in/sheet.png","/out/sheet.png",'
        '"SINGLE_CHOICE_CONFLICT_REVIEW","q1","ABCD","C","0.820",'
        '"RESOLVED_CANDIDATE","single_choice_conflict",'
        '"gap,delta_from_blank,center_density","4.20","",'
        '"0.080","0.250","0.620","6.000","0.750","1.000"'
    ]
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python -m pytest \
  tests/test_weak_fill_features.py::test_review_csv_header_includes_review_type_and_original_value \
  tests/test_weak_fill_features.py::test_append_review_rows_writes_review_type_and_original_value -q
```

Expected: both tests fail because `review_type` and `original_value` are not yet in the CSV schema/writer.

- [ ] **Step 4: Extend `src/utils/file.py` header**

Update `ns.weakFillReviewCols` in `setup_outputs_for_template` to this exact list:

```python
    ns.weakFillReviewCols = [
        "file_id",
        "input_path",
        "output_path",
        "review_type",
        "field",
        "original_value",
        "candidate",
        "confidence",
        "status",
        "reason",
        "evidence",
        "score",
        "legacy_rejection",
        "ambiguity",
        "density_gap",
        "center_density",
        "center_edge_ratio",
        "threshold_vote_ratio",
        "multiscale_stability",
    ]
```

- [ ] **Step 5: Extend `src/entry.py` row writer**

In `append_weak_fill_review_rows`, update the row list prefix to:

```python
                review.get("review_type", "WEAK_MARK_REVIEW"),
                review.get("field", ""),
                review.get("original_value", ""),
                review.get("candidate", ""),
```

The first fields in each row should be:

```python
                img_name,
                file_path,
                output_path,
                review.get("review_type", "WEAK_MARK_REVIEW"),
                review.get("field", ""),
                review.get("original_value", ""),
                review.get("candidate", ""),
                _format_review_float(review.get("confidence", 0.0), 3),
```

- [ ] **Step 6: Run Task 1 tests and verify they pass**

Run the same command from Step 3.

Expected: both tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/utils/file.py src/entry.py tests/test_weak_fill_features.py
git commit -m "feat: extend review candidate csv schema"
```

---

### Task 2: Add single-choice conflict review records

**Files:**
- Modify: `src/core.py`
- Test: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Write failing conflict review tests**

Add these tests to `tests/test_weak_fill_features.py`:

```python
def test_single_choice_conflict_records_review_candidate_without_changing_result():
    ops = make_ops(resolve_single_choice_conflicts=True)
    field_block = FakeFieldBlock()
    bubbles = make_bubbles()
    detected = [bubbles[0], bubbles[1], bubbles[2], bubbles[3]]

    result = ops.resolve_single_choice_conflict(
        field_block,
        bubbles,
        [200.0, 212.0, 178.0, 215.0],
        detected,
    )

    assert result == [bubbles[2]]
    assert len(ops.last_weak_fill_reviews) == 1
    review = ops.last_weak_fill_reviews[0]
    assert review["review_type"] == "SINGLE_CHOICE_CONFLICT_REVIEW"
    assert review["field"] == "q1"
    assert review["original_value"] == "ABCD"
    assert review["candidate"] == "C"
    assert review["status"] == "RESOLVED_CANDIDATE"
    assert review["reason"] == "single_choice_conflict"
    assert 0.0 <= review["confidence"] <= 1.0


def test_multi_select_conflict_does_not_record_single_choice_review():
    ops = make_ops(resolve_single_choice_conflicts=True)
    field_block = FakeFieldBlock(multi_select=True)
    bubbles = make_bubbles()
    detected = [bubbles[0], bubbles[1]]

    result = ops.resolve_single_choice_conflict(
        field_block,
        bubbles,
        [180.0, 181.0, 220.0, 225.0],
        detected,
    )

    assert result == detected
    assert ops.last_weak_fill_reviews == []
```

If `FakeFieldBlock` does not accept `multi_select`, update the helper class constructor to accept `multi_select=False` and assign `self.multi_select = multi_select`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python -m pytest \
  tests/test_weak_fill_features.py::test_single_choice_conflict_records_review_candidate_without_changing_result \
  tests/test_weak_fill_features.py::test_multi_select_conflict_does_not_record_single_choice_review -q
```

Expected: first test fails because no conflict review record is appended.

- [ ] **Step 3: Add conflict confidence helper in `src/core.py`**

Add this method inside `ImageInstanceOps`, near `get_weak_fill_confidence`:

```python
    @staticmethod
    def get_single_choice_conflict_confidence(diagnostics):
        """Convert single-choice conflict separation into a bounded confidence."""
        gap_component = min(max(diagnostics.get("gap", 0.0), 0.0) / 20.0, 1.0)
        delta_component = min(
            max(diagnostics.get("delta_from_blank", 0.0), 0.0) / 40.0, 1.0
        )
        confidence = gap_component * 0.55 + delta_component * 0.45
        return max(0.0, min(confidence, 1.0))
```

- [ ] **Step 4: Add conflict review appender in `src/core.py`**

Add this method inside `ImageInstanceOps`:

```python
    def append_single_choice_conflict_review(
        self, field_label, original_value, candidate, diagnostics, status
    ):
        confidence = self.get_single_choice_conflict_confidence(diagnostics)
        self.last_weak_fill_reviews.append(
            {
                "review_type": "SINGLE_CHOICE_CONFLICT_REVIEW",
                "field": field_label,
                "original_value": original_value,
                "candidate": candidate,
                "status": status,
                "confidence": confidence,
                "score": confidence * 5.0,
                "reason": "single_choice_conflict",
                "legacy_rejection": "",
                "evidence": "gap,delta_from_blank",
                "ambiguity": 1.0 - confidence,
                "density_gap": 0.0,
                "center_density": 0.0,
                "center_edge_ratio": 0.0,
                "threshold_vote_ratio": 0.0,
                "multiscale_stability": 0.0,
            }
        )
```

- [ ] **Step 5: Call conflict appender in `resolve_single_choice_conflict`**

Before returning from the resolved branch, add:

```python
            self.append_single_choice_conflict_review(
                field_label,
                "".join(b.field_value for b in detected_bubbles),
                darkest_bubble.field_value,
                diagnostics,
                "RESOLVED_CANDIDATE",
            )
```

Before returning from the unresolved branch, add:

```python
        self.append_single_choice_conflict_review(
            field_label,
            "".join(b.field_value for b in detected_bubbles),
            darkest_bubble.field_value,
            diagnostics,
            "LOW_CONFIDENCE",
        )
```

- [ ] **Step 6: Run Task 2 tests and verify they pass**

Run the same command from Step 2.

Expected: both tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/core.py tests/test_weak_fill_features.py
git commit -m "feat: record single-choice conflict reviews"
```

---

### Task 3: Add ID review records

**Files:**
- Modify: `src/core.py`
- Test: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Write failing ID review test**

Add this test to `tests/test_weak_fill_features.py`:

```python
def test_weak_identifier_candidate_records_id_review():
    ops = make_ops()
    ops.tuning_config.weak_identifier_params.enabled = True
    ops.tuning_config.weak_identifier_params.labels = []
    ops.tuning_config.weak_identifier_params.exclude_labels = []
    ops.tuning_config.weak_identifier_params.min_gap = 8
    ops.tuning_config.weak_identifier_params.min_delta_from_blank = 15
    ops.tuning_config.weak_identifier_params.max_mean = 220
    ops.tuning_config.weak_identifier_params.adaptive_max_mean = 230
    ops.tuning_config.weak_identifier_params.supported_field_types = ["QTYPE_INT"]

    field_block = FakeFieldBlock(field_type="QTYPE_INT", direction="vertical")
    bubbles = [
        FakeBubble("id7", str(i), x=10, y=10 + i * 6)
        for i in range(10)
    ]

    result = ops.get_weak_identifier_bubble(
        field_block,
        bubbles,
        [222, 221, 220, 219, 218, 217, 216, 180, 215, 214],
        [],
        make_image(fill_value=170),
        {"mean": 225.0, "std": 2.0},
    )

    assert result is not None
    assert result.field_value == "7"
    assert len(ops.last_weak_fill_reviews) == 1
    review = ops.last_weak_fill_reviews[0]
    assert review["review_type"] == "ID_REVIEW"
    assert review["field"] == "id7"
    assert review["original_value"] == ""
    assert review["candidate"] == "7"
    assert review["status"] == "RESOLVED_CANDIDATE"
    assert review["reason"] == "weak_identifier_candidate"
    assert 0.0 <= review["confidence"] <= 1.0
```

If `FakeFieldBlock` does not accept `field_type` or `direction`, update its constructor to accept and assign those values.

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python -m pytest \
  tests/test_weak_fill_features.py::test_weak_identifier_candidate_records_id_review -q
```

Expected: fails because `ID_REVIEW` is not recorded.

- [ ] **Step 3: Add ID confidence helper in `src/core.py`**

Add this method near the other confidence helpers:

```python
    @staticmethod
    def get_identifier_review_confidence(diagnostics):
        gap_component = min(max(diagnostics.get("gap", 0.0), 0.0) / 25.0, 1.0)
        delta_component = min(
            max(diagnostics.get("delta_from_blank", 0.0), 0.0) / 45.0, 1.0
        )
        page_component = min(max(diagnostics.get("page_z_score", 0.0), 0.0) / 10.0, 1.0)
        density_component = min(
            max(diagnostics.get("density_gap", 0.0), 0.0) / 0.25, 1.0
        )
        confidence = (
            gap_component * 0.30
            + delta_component * 0.30
            + page_component * 0.20
            + density_component * 0.20
        )
        return max(0.0, min(confidence, 1.0))
```

- [ ] **Step 4: Add ID review appender in `src/core.py`**

Add this method inside `ImageInstanceOps`:

```python
    def append_identifier_review(self, field_label, candidate, diagnostics, status):
        confidence = self.get_identifier_review_confidence(diagnostics)
        self.last_weak_fill_reviews.append(
            {
                "review_type": "ID_REVIEW",
                "field": field_label,
                "original_value": "",
                "candidate": candidate,
                "status": status,
                "confidence": confidence,
                "score": confidence * 5.0,
                "reason": "weak_identifier_candidate",
                "legacy_rejection": "",
                "evidence": "gap,delta_from_blank,page_z,density_gap",
                "ambiguity": 1.0 - confidence,
                "density_gap": diagnostics.get("density_gap", 0.0),
                "center_density": diagnostics.get("darkest_center_density", 0.0),
                "center_edge_ratio": diagnostics.get("darkest_center_edge_ratio", 0.0),
                "threshold_vote_ratio": 0.0,
                "multiscale_stability": 0.0,
            }
        )
```

- [ ] **Step 5: Call ID appender before returning accepted weak identifier bubble**

In `get_weak_identifier_bubble`, before `return weak_bubble`, add:

```python
        self.append_identifier_review(
            field_label,
            weak_bubble.field_value,
            diagnostics,
            "RESOLVED_CANDIDATE",
        )
```

- [ ] **Step 6: Run Task 3 test and verify it passes**

Run the same command from Step 2.

Expected: pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/core.py tests/test_weak_fill_features.py
git commit -m "feat: record weak identifier reviews"
```

---

### Task 4: Enable observation-only single-choice conflict review in config

**Files:**
- Modify: `inputs/config.json`
- Test: regression command output

- [ ] **Step 1: Add conflict config keys without changing global thresholds**

Update `inputs/config.json` under `weak_mark_params` to include:

```json
    "resolve_single_choice_conflicts": true,
    "conflict_min_gap": 5,
    "conflict_min_delta_from_blank": 20,
```

Do not change `threshold_params`. Do not modify multi-select settings.

- [ ] **Step 2: Run weak scenario regression only**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python scripts/run_omr_regression.py --scenario weak | tee jcode_regression_summary_after_review_extension_weak.txt
```

Expected: command completes. Inspect `outputs_jcode_regression_weak/Results/WeakFillReview.csv` and confirm it has rows with `review_type=SINGLE_CHOICE_CONFLICT_REVIEW`.

- [ ] **Step 3: Decide if observation-only mode changed Results**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
python - <<'PY'
import csv, glob
p = sorted(glob.glob('outputs_jcode_regression_weak/Results/Results_*.csv'))[-1]
with open(p, newline='') as handle:
    for row in csv.DictReader(handle):
        if row['file_id'] == 'MX-M3658N_20260731_162311_001.png':
            print('q1=', row.get('q1'))
            print('q2=', row.get('q2'))
            print('q5=', row.get('q5'))
PY
```

Expected for this task: record the observed values. If `q1/q2` change to single candidates, note that existing `resolve_single_choice_conflict` is not observation-only and this must be documented. If strict Results stability is required, stop and revise the implementation so review record creation is decoupled from answer correction.

- [ ] **Step 4: Commit config only if behavior matches approved scope**

If Results stability remains acceptable under the approved design, run:

```bash
git add inputs/config.json
git commit -m "config: enable single-choice conflict review"
```

If Results changed and the approved scope requires observation-only behavior, do not commit. Instead add a follow-up Task 4b to split review observation from conflict answer resolution.

---

### Task 5: Full validation and documentation

**Files:**
- Create: `docs/weak-fill-optimization/regression-summaries/2026-08-01-review-confidence-extension.md`

- [ ] **Step 1: Run all existing tests**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python -m pytest tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run four-scenario regression**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
PYTHONPATH=. python scripts/run_omr_regression.py | tee jcode_regression_summary_after_review_confidence_extension.txt
```

Expected: command completes for weak, normal, underfill, and overflow.

- [ ] **Step 3: Summarize auxiliary review rows**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
. .venv/bin/activate
for s in weak normal underfill overflow; do
  f=outputs_jcode_regression_${s}/Results/WeakFillReview.csv
  echo SCENARIO $s
  python - <<'PY' "$f"
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], newline='')))
print('rows=', len(rows))
counts = {}
for row in rows:
    counts[row.get('review_type', '')] = counts.get(row.get('review_type', ''), 0) + 1
print('types=', counts)
for row in rows[:20]:
    print(row.get('file_id'), row.get('review_type'), row.get('field'), row.get('original_value'), row.get('candidate'), row.get('confidence'), row.get('status'))
PY
done
```

Expected: weak has weak mark and conflict review rows. Multi-select questions should not appear as single-choice conflict rows if their template field block has `multi_select=True`.

- [ ] **Step 4: Write regression summary document**

Create `docs/weak-fill-optimization/regression-summaries/2026-08-01-review-confidence-extension.md` with this structure:

```markdown
# 2026-08-01 复核置信度输出扩展回归摘要

## 变更范围

- 扩展 `WeakFillReview.csv`，新增 `review_type` 和 `original_value`。
- 新增 `SINGLE_CHOICE_CONFLICT_REVIEW`。
- 新增 `ID_REVIEW`。
- 说明是否启用了单选冲突自动解析，以及是否影响 Results。

## 验证命令

列出 pytest 和四场景回归命令。

## Results CSV 指标

粘贴四场景 rows/id_blank_cells/q_blank_cells/blank_cells/blank_rows。

## Review CSV 分布

列出 weak/normal/underfill/overflow 的 review_type 行数。

## 人工标注样例

- `MX-M3658N_20260731_162311_001.png q1` 实际 `C`。
- `MX-M3658N_20260731_162311_001.png q2` 实际 `A`。
- `MX-M3658N_20260731_162311_001.png q5` 实际 `D`。
- `q9/q10/q11` 是正确多选题，不应被单选冲突解析覆盖。

## 结论

说明当前是否只适合作为人工复核，或是否可以进入保守自动修正设计。
```

- [ ] **Step 5: Commit summary**

```bash
git add docs/weak-fill-optimization/regression-summaries/2026-08-01-review-confidence-extension.md
git commit -m "docs: summarize review confidence extension"
```

- [ ] **Step 6: Final status check**

Run:

```bash
cd /Volumes/wdata/work/tech/OMRChecker
rtk git status --short || git status --short
```

Expected: only unrelated pre-existing files remain unstaged.
