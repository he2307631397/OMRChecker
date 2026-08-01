# General Weak-fill Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve weak-fill recognition through a general feature-based fallback while preserving normal, overflow, underfilled, identifier, and multi-select behavior.

**Architecture:** Keep the normal OMR thresholding path unchanged. Add reusable bubble feature extraction and a conservative single-choice weak-fill confidence decision that only runs for blank non-multiSelect `QTYPE_MCQ4` fields. Add a regression runner that copies config and assets into isolated run directories and reports scenario metrics.

**Tech Stack:** Python 3, OpenCV, NumPy, existing OMRChecker CLI, pytest-compatible unit tests using lightweight fake field/bubble objects.

---

## File Structure

- Modify `src/core.py`: add feature helpers and replace the current single-choice weak mark support check with a score-based decision.
- Modify `src/defaults/config.py`: add conservative guardrail defaults for score-based weak-fill fallback.
- Modify `src/schemas/config_schema.py`: allow the new config fields.
- Create `tests/test_weak_fill_features.py`: unit tests for general feature extraction and confidence decisions.
- Create `scripts/run_omr_regression.py`: repeatable four-scenario runner and CSV/log summarizer.
- Create `docs/general-weak-fill-optimization.md`: final validation notes after implementation.


## Non-specialization Guardrails

- Do not hard-code file names, directories, page indices, coordinates, answers, candidate labels, or sample exceptions.
- Do not lower global thresholding parameters to force weak marks through the primary threshold path.
- Any tuning must be expressed through reusable page, field, and bubble features that apply across all scenarios.

## Task 1: Unit Tests for General Weak-fill Feature Decisions

**Files:**
- Create: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Create test directory and failing tests**

Create `tests/test_weak_fill_features.py` with:

```python
from dataclasses import dataclass

import numpy as np
from dotmap import DotMap

from src.core import ImageInstanceOps


@dataclass
class FakeBubble:
    field_label: str
    field_value: str
    x: int = 0
    y: int = 0
    multi_select: bool = False


@dataclass
class FakeFieldBlock:
    field_type: str = "QTYPE_MCQ4"
    multi_select: bool = False
    bubble_dimensions: tuple[int, int] = (30, 18)
    shift: int = 0


def make_ops(**weak_overrides):
    params = {
        "enabled": True,
        "min_gap": 10,
        "min_delta_from_blank": 25,
        "adaptive_min_delta_from_blank": 12,
        "min_delta_from_page_blank": 20,
        "min_page_z_score": 2.0,
        "min_dark_pixel_ratio": 0.08,
        "min_density_gap": 0.03,
        "max_mean": 215,
        "supported_field_types": ["QTYPE_MCQ4"],
        "exclude_labels": [],
        "weak_fill_score_enabled": True,
        "weak_fill_min_score": 3.0,
        "weak_fill_review_min_score": 2.0,
        "weak_fill_min_page_delta": 12,
        "weak_fill_min_center_density": 0.12,
        "weak_fill_min_dark_ratio": 0.12,
        "weak_fill_max_ambiguity": 1.25,
    }
    params.update(weak_overrides)
    return ImageInstanceOps(DotMap({"outputs": {"save_image_level": 0}, "weak_mark_params": params}))


def make_image(fill_value=180, blank_value=240):
    image = np.full((30, 140), blank_value, dtype=np.uint8)
    image[5:13, 8:22] = fill_value
    return image


def test_feature_decision_accepts_general_page_supported_weak_mark():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = [FakeBubble("q1", "A"), FakeBubble("q1", "B", x=35), FakeBubble("q1", "C", x=70), FakeBubble("q1", "D", x=105)]
    diagnostics = ops.get_field_diagnostics([202.7, 208.6, 217.0, 219.0])
    diagnostics = ops.enrich_diagnostics_with_density(
        make_image(fill_value=180), field, bubbles, [202.7, 208.6, 217.0, 219.0], diagnostics, {"mean": 223.6, "std": 1.4}
    )

    decision = ops.get_single_choice_weak_fill_decision(diagnostics)

    assert decision["status"] == "WEAK_MARK"
    assert decision["score"] >= 3.0
    assert decision["reason"] == "feature_score"


def test_feature_decision_rejects_ambiguous_density_even_with_page_support():
    ops = make_ops()
    field = FakeFieldBlock()
    bubbles = [FakeBubble("q1", "A"), FakeBubble("q1", "B", x=35), FakeBubble("q1", "C", x=70), FakeBubble("q1", "D", x=105)]
    diagnostics = ops.get_field_diagnostics([202.7, 203.1, 203.3, 203.4])
    diagnostics = ops.enrich_diagnostics_with_density(
        np.full((30, 140), 190, dtype=np.uint8), field, bubbles, [202.7, 203.1, 203.3, 203.4], diagnostics, {"mean": 223.6, "std": 1.4}
    )

    decision = ops.get_single_choice_weak_fill_decision(diagnostics)

    assert decision["status"] in {"REVIEW", "EMPTY"}
    assert decision["status"] != "WEAK_MARK"


def test_existing_disabled_config_keeps_fallback_off():
    ops = make_ops(enabled=False)
    assert not ops.tuning_config.weak_mark_params.enabled
```

- [ ] **Step 2: Run tests and verify they fail before implementation**

Run:

```bash
. .venv/bin/activate
pytest tests/test_weak_fill_features.py -v
```

Expected: fails because `get_single_choice_weak_fill_decision` is not defined.

- [ ] **Step 3: Commit failing tests only if the project practice allows red commits**

Do not commit failing tests alone unless explicitly using a red-green commit style. Otherwise keep them unstaged until Task 2 passes.

## Task 2: Add Bubble Density Features and Score Decision

**Files:**
- Modify: `src/core.py`
- Test: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Add ROI density helper methods in `ImageInstanceOps`**

Add these methods near `get_candidate_density` in `src/core.py`:

```python
    @staticmethod
    def get_candidate_density_features(image, field_block, bubble, blank_baseline):
        box_w, box_h = field_block.bubble_dimensions
        x, y = (bubble.x + field_block.shift, bubble.y)
        roi = image[y : y + box_h, x : x + box_w]
        if roi.size == 0:
            return {"dark_ratio": 0.0, "center_density": 0.0, "edge_density": 0.0, "center_edge_ratio": 0.0}

        threshold = max(0, blank_baseline - 20)
        dark_mask = roi < threshold
        dark_ratio = float(np.mean(dark_mask))

        pad_x = max(1, int(box_w / 4))
        pad_y = max(1, int(box_h / 4))
        center = dark_mask[pad_y : box_h - pad_y, pad_x : box_w - pad_x]
        center_density = float(np.mean(center)) if center.size else 0.0

        edge_mask = dark_mask.copy()
        if center.size:
            edge_mask[pad_y : box_h - pad_y, pad_x : box_w - pad_x] = False
        edge_count = edge_mask.size - center.size
        edge_density = float(np.sum(edge_mask) / max(edge_count, 1))
        center_edge_ratio = center_density / max(edge_density, 0.01)

        return {
            "dark_ratio": dark_ratio,
            "center_density": center_density,
            "edge_density": edge_density,
            "center_edge_ratio": center_edge_ratio,
        }
```

- [ ] **Step 2: Extend `enrich_diagnostics_with_density`**

Inside the loop over `field_block_bubbles`, call `get_candidate_density_features` and collect `dark_ratio`, `center_density`, `edge_density`, and `center_edge_ratio` lists. Update `diagnostics` with darkest candidate values:

```python
        density_features = []
        for bubble in field_block_bubbles:
            density_features.append(
                self.get_candidate_density_features(
                    image, field_block, bubble, diagnostics["blank_baseline"]
                )
            )
```

Then add to `diagnostics.update`:

```python
                "dark_ratios": [item["dark_ratio"] for item in density_features],
                "center_densities": [item["center_density"] for item in density_features],
                "edge_densities": [item["edge_density"] for item in density_features],
                "center_edge_ratios": [item["center_edge_ratio"] for item in density_features],
                "darkest_dark_ratio": density_features[darkest_index]["dark_ratio"] if density_features else 0.0,
                "darkest_center_density": density_features[darkest_index]["center_density"] if density_features else 0.0,
                "darkest_edge_density": density_features[darkest_index]["edge_density"] if density_features else 0.0,
                "darkest_center_edge_ratio": density_features[darkest_index]["center_edge_ratio"] if density_features else 0.0,
```

- [ ] **Step 3: Add score decision method**

Add this method before `get_weak_marked_bubble`:

```python
    def get_single_choice_weak_fill_decision(self, diagnostics):
        weak_mark_params = self.tuning_config.weak_mark_params
        if not getattr(weak_mark_params, "weak_fill_score_enabled", False):
            return {"status": "LEGACY", "score": 0.0, "reason": "score_disabled"}

        page_delta = diagnostics["delta_from_page_blank"]
        page_z = diagnostics["page_z_score"]
        local_delta = diagnostics["delta_from_blank"]
        gap = diagnostics["gap"]
        dark_ratio = diagnostics.get("darkest_dark_ratio", diagnostics.get("darkest_density", 0.0))
        center_density = diagnostics.get("darkest_center_density", diagnostics.get("darkest_density", 0.0))
        center_edge_ratio = diagnostics.get("darkest_center_edge_ratio", 0.0)
        density_gap = diagnostics.get("density_gap", 0.0)

        score = 0.0
        reasons = []
        if page_delta >= weak_mark_params.weak_fill_min_page_delta:
            score += 1.0
            reasons.append("page_delta")
        if page_z >= weak_mark_params.min_page_z_score:
            score += 1.0
            reasons.append("page_z")
        if dark_ratio >= weak_mark_params.weak_fill_min_dark_ratio:
            score += 1.0
            reasons.append("dark_ratio")
        if center_density >= weak_mark_params.weak_fill_min_center_density:
            score += 1.0
            reasons.append("center_density")
        if center_edge_ratio >= 1.0:
            score += 0.5
            reasons.append("center_edge")
        if local_delta >= weak_mark_params.adaptive_min_delta_from_blank:
            score += 0.75
            reasons.append("local_delta")
        if gap >= weak_mark_params.min_gap:
            score += 0.75
            reasons.append("gap")
        if density_gap >= weak_mark_params.min_density_gap:
            score += 0.5
            reasons.append("density_gap")

        ambiguity = 0.0
        if gap < weak_mark_params.min_gap:
            ambiguity += (weak_mark_params.min_gap - gap) / max(weak_mark_params.min_gap, 1)
        if density_gap < 0:
            ambiguity += abs(density_gap) * 2

        if ambiguity > weak_mark_params.weak_fill_max_ambiguity:
            return {"status": "REVIEW", "score": score, "reason": "ambiguous", "evidence": reasons, "ambiguity": ambiguity}
        if score >= weak_mark_params.weak_fill_min_score:
            return {"status": "WEAK_MARK", "score": score, "reason": "feature_score", "evidence": reasons, "ambiguity": ambiguity}
        if score >= weak_mark_params.weak_fill_review_min_score:
            return {"status": "REVIEW", "score": score, "reason": "low_score", "evidence": reasons, "ambiguity": ambiguity}
        return {"status": "EMPTY", "score": score, "reason": "low_score", "evidence": reasons, "ambiguity": ambiguity}
```

- [ ] **Step 4: Run unit tests**

Run:

```bash
. .venv/bin/activate
pytest tests/test_weak_fill_features.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit feature helpers and tests**

```bash
git add src/core.py tests/test_weak_fill_features.py
git commit -m "feat: add weak-fill feature scoring helpers"
```

## Task 3: Integrate Score Decision into Blank-only Single-choice Fallback

**Files:**
- Modify: `src/core.py`
- Test: `tests/test_weak_fill_features.py`

- [ ] **Step 1: Update `get_weak_marked_bubble` to use score decision first**

After diagnostics are enriched and before legacy rejection logic, add:

```python
        score_decision = self.get_single_choice_weak_fill_decision(diagnostics)
        if score_decision["status"] == "WEAK_MARK":
            weak_bubble = field_block_bubbles[darkest_index]
            logger.warning(
                f"Weak mark fallback: field '{field_label}' -> "
                f"'{weak_bubble.field_value}' "
                f"(status=WEAK_MARK, score={score_decision['score']:.2f}, "
                f"reason={score_decision['reason']}, "
                f"evidence={','.join(score_decision['evidence'])}, "
                f"ambiguity={score_decision['ambiguity']:.2f}, "
                f"darkest_mean={darkest_mean:.2f}, "
                f"second_darkest_mean={second_darkest_mean:.2f}, gap={gap:.2f}, "
                f"blank_baseline={blank_baseline:.2f}, delta={delta_from_blank:.2f}, "
                f"page_blank_mean={diagnostics['page_blank_mean']:.2f}, "
                f"page_delta={diagnostics['delta_from_page_blank']:.2f}, "
                f"page_z={diagnostics['page_z_score']:.2f}, "
                f"dark_ratio={diagnostics.get('darkest_dark_ratio', 0.0):.3f}, "
                f"center_density={diagnostics.get('darkest_center_density', 0.0):.3f}, "
                f"edge_density={diagnostics.get('darkest_edge_density', 0.0):.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f})"
            )
            return weak_bubble
        if score_decision["status"] == "REVIEW":
            logger.info(
                f"Weak mark candidate review: field '{field_label}' "
                f"score={score_decision['score']:.2f}, reason={score_decision['reason']}, "
                f"evidence={','.join(score_decision['evidence'])}, "
                f"ambiguity={score_decision['ambiguity']:.2f}, "
                f"darkest_mean={darkest_mean:.2f}, second_darkest_mean={second_darkest_mean:.2f}, "
                f"gap={gap:.2f}, blank_baseline={blank_baseline:.2f}, "
                f"delta={delta_from_blank:.2f}, page_z={diagnostics['page_z_score']:.2f}, "
                f"dark_ratio={diagnostics.get('darkest_dark_ratio', 0.0):.3f}, "
                f"center_density={diagnostics.get('darkest_center_density', 0.0):.3f}, "
                f"density_gap={diagnostics['density_gap']:.3f}"
            )
            return None
```

Keep the legacy logic after this block so old configurations with `weak_fill_score_enabled=false` behave as before.

- [ ] **Step 2: Run unit tests**

Run:

```bash
. .venv/bin/activate
pytest tests/test_weak_fill_features.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run one weak smoke case**

Run:

```bash
. .venv/bin/activate
python main.py -i .jcode_runs/weak_smoke -o outputs_jcode_weak_smoke_after
```

Expected: command exits 0. Logs show either `Weak mark fallback` or `Weak mark candidate review` with score diagnostics.

- [ ] **Step 4: Commit integration**

```bash
git add src/core.py
git commit -m "feat: apply feature-scored weak mark fallback"
```

## Task 4: Add Config Defaults and Schema Fields

**Files:**
- Modify: `src/defaults/config.py`
- Modify: `src/schemas/config_schema.py`
- Modify: `inputs/config.json`

- [ ] **Step 1: Add defaults**

In `src/defaults/config.py`, inside `weak_mark_params`, add:

```python
            "weak_fill_score_enabled": False,
            "weak_fill_min_score": 3.5,
            "weak_fill_review_min_score": 2.5,
            "weak_fill_min_page_delta": 12,
            "weak_fill_min_center_density": 0.12,
            "weak_fill_min_dark_ratio": 0.12,
            "weak_fill_max_ambiguity": 1.25,
```

Default remains disabled to avoid changing existing users unexpectedly.

- [ ] **Step 2: Add schema fields**

In `src/schemas/config_schema.py`, inside `weak_mark_params.properties`, add:

```python
                "weak_fill_score_enabled": {"type": "boolean"},
                "weak_fill_min_score": {"type": "number", "minimum": 0, "maximum": 10},
                "weak_fill_review_min_score": {"type": "number", "minimum": 0, "maximum": 10},
                "weak_fill_min_page_delta": {"type": "number", "minimum": 0, "maximum": 100},
                "weak_fill_min_center_density": {"type": "number", "minimum": 0, "maximum": 1},
                "weak_fill_min_dark_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                "weak_fill_max_ambiguity": {"type": "number", "minimum": 0, "maximum": 10},
```

- [ ] **Step 3: Enable score fallback in `inputs/config.json` for validation input**

Add these keys under `weak_mark_params`:

```json
    "weak_fill_score_enabled": true,
    "weak_fill_min_score": 3.5,
    "weak_fill_review_min_score": 2.5,
    "weak_fill_min_page_delta": 12,
    "weak_fill_min_center_density": 0.12,
    "weak_fill_min_dark_ratio": 0.12,
    "weak_fill_max_ambiguity": 1.25
```

- [ ] **Step 4: Validate JSON and schema loading**

Run:

```bash
python3 -m json.tool inputs/config.json >/tmp/omr_config_valid.json
python3 -m json.tool inputs/template.json >/tmp/omr_template_valid.json
. .venv/bin/activate
python main.py -i .jcode_runs/weak_smoke -o outputs_jcode_schema_smoke
```

Expected: JSON validation succeeds and smoke run exits 0.

- [ ] **Step 5: Commit config fields**

```bash
git add src/defaults/config.py src/schemas/config_schema.py inputs/config.json
git commit -m "feat: configure feature-scored weak fill fallback"
```

## Task 5: Add Regression Runner

**Files:**
- Create: `scripts/run_omr_regression.py`

- [ ] **Step 1: Create runner script**

Create `scripts/run_omr_regression.py`:

```python
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCENARIOS = {
    "weak": "淡涂答题卡归档",
    "normal": "正常填涂测试答题卡归档",
    "underfill": "没涂满答题卡归档",
    "overflow": "涂超出答题卡归档",
}

FALLBACK_PATTERNS = [
    "Weak identifier fallback",
    "Weak mark fallback",
    "Weak multi-mark fallback",
    "Weak multi full-select fallback",
    "Weak mark candidate review",
    "Single-choice conflict",
]


def prepare_run_dir(root: Path, scenario: str, asset_dir: str) -> Path:
    run_dir = root / f"baseline_{scenario}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    for name in ["config.json", "template.json", "reference.png"]:
        shutil.copy2(Path("inputs") / name, run_dir / name)
    for pdf in sorted((Path("docs/assets") / asset_dir).glob("*.pdf")):
        shutil.copy2(pdf, run_dir / pdf.name)
    return run_dir


def summarize_csv(output_dir: Path) -> dict:
    csvs = sorted((output_dir / "Results").glob("Results_*.csv"))
    if not csvs:
        return {"rows": 0, "id_blank_cells": 0, "q_blank_cells": 0, "blank_cells": 0, "blank_rows": 0, "csv": ""}
    result_csv = csvs[-1]
    rows = list(csv.DictReader(result_csv.open()))
    id_cols = [c for c in rows[0] if c.startswith("id")] if rows else []
    q_cols = [c for c in rows[0] if c.startswith("q")] if rows else []
    blanks = []
    for row in rows:
        file_id = row.get("file_id") or next(iter(row.values()), "")
        for col in id_cols + q_cols:
            if not (row.get(col, "") or "").strip():
                blanks.append((file_id, col))
    return {
        "rows": len(rows),
        "id_blank_cells": sum(col.startswith("id") for _, col in blanks),
        "q_blank_cells": sum(col.startswith("q") for _, col in blanks),
        "blank_cells": len(blanks),
        "blank_rows": len({file_id for file_id, _ in blanks}),
        "csv": str(result_csv),
        "blanks": blanks,
    }


def summarize_log(log_path: Path) -> dict:
    text = log_path.read_text(errors="ignore") if log_path.exists() else ""
    return {pattern: len(re.findall(pattern, text)) for pattern in FALLBACK_PATTERNS}


def run_scenario(scenario: str, run_dir: Path) -> tuple[dict, dict]:
    output_dir = Path(f"outputs_jcode_regression_{scenario}")
    log_path = Path(f"jcode_regression_{scenario}.log")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    with log_path.open("w") as log_file:
        completed = subprocess.run(
            [sys.executable, "main.py", "-i", str(run_dir), "-o", str(output_dir)],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        raise SystemExit(f"{scenario} failed with exit {completed.returncode}; see {log_path}")
    return summarize_csv(output_dir), summarize_log(log_path)


def main() -> None:
    run_root = Path(".jcode_runs/regression")
    rows = []
    for scenario, asset_dir in SCENARIOS.items():
        run_dir = prepare_run_dir(run_root, scenario, asset_dir)
        summary, fallbacks = run_scenario(scenario, run_dir)
        rows.append((scenario, summary, fallbacks))

    for scenario, summary, fallbacks in rows:
        print(f"SCENARIO {scenario}")
        print(
            " rows={rows} id_blank_cells={id_blank_cells} q_blank_cells={q_blank_cells} "
            "blank_cells={blank_cells} blank_rows={blank_rows}".format(**summary)
        )
        print(f" csv={summary['csv']}")
        print(f" fallbacks={fallbacks}")
        for file_id, col in summary.get("blanks", [])[:40]:
            print(f" blank {file_id} {col}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run runner**

Run:

```bash
. .venv/bin/activate
python scripts/run_omr_regression.py
```

Expected: prints all four scenarios and exits 0.

- [ ] **Step 3: Commit runner**

```bash
git add scripts/run_omr_regression.py
git commit -m "test: add OMR scenario regression runner"
```

## Task 6: Full Regression Validation and Documentation

**Files:**
- Create: `docs/general-weak-fill-optimization.md`
- Generated but do not commit unless desired: `jcode_regression_*.log`, `outputs_jcode_regression_*`, `.jcode_runs/regression`

- [ ] **Step 1: Run full regression**

Run:

```bash
. .venv/bin/activate
python scripts/run_omr_regression.py | tee jcode_regression_summary.txt
```

Expected gates:

```text
normal: rows=56 id_blank_cells=0 q_blank_cells=0
underfill: no new identifier auto-fill for intentionally blank row
overflow: rows=4 id_blank_cells=0 q_blank_cells=0
weak: blank_cells less than baseline 4, or additional REVIEW logs explain remaining blanks
```

- [ ] **Step 2: Inspect normal scenario diff risk**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import csv
p=sorted(Path('outputs_jcode_regression_normal/Results').glob('Results_*.csv'))[-1]
rows=list(csv.DictReader(p.open()))
print('normal_rows', len(rows))
print('normal_blank_cells', sum(1 for r in rows for k,v in r.items() if (k.startswith('id') or k.startswith('q')) and not (v or '').strip()))
PY
```

Expected:

```text
normal_rows 56
normal_blank_cells 0
```

- [ ] **Step 3: Write validation doc**

Create `docs/general-weak-fill-optimization.md` with:

```markdown
# General Weak-fill Optimization Validation

## Goal

Improve weak-fill recognition through general feature scoring without sample-specific tuning.

## Regression Command

```bash
. .venv/bin/activate
python scripts/run_omr_regression.py
```

## Results

Paste the final four-scenario summary here after the run.

## Safety Review

- Normal-fill 56 gate:
- Weak-fill 10 improvement:
- Underfilled 4 gate:
- Overflow 4 gate:
- Fallback/review log assessment:

## Conclusion

State whether the change is safe to keep, needs threshold adjustment, or should be limited to review diagnostics.
```

- [ ] **Step 4: Commit validation doc if gates pass**

```bash
git add docs/general-weak-fill-optimization.md
# Include jcode_regression_summary.txt only if the repository wants run artifacts committed.
git commit -m "docs: record general weak-fill validation"
```

- [ ] **Step 5: Final status check**

Run:

```bash
rtk git status --short
rtk git log --oneline -5
```

Expected: only user-owned untracked assets or intentionally generated run outputs remain unstaged.
