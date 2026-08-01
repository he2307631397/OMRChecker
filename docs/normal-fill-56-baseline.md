# Normal-fill 56-sheet Baseline Test Report

## Purpose

This document records the current normal-fill recognition baseline. It is intended as the comparison reference for later weak-fill, abnormal-fill, shifted-scan, and other edge-case test reports.

## Branch and Version

- Branch: `robyn-web-service`
- Relevant commits:
  - `feb48dd Add weak identifier fallback detection`
  - `f82463f Merge branch 'alignment-experiments' into robyn-web-service`
  - `646061a Add adaptive full-select fallback threshold`
  - `09d3b26 Support template-level multi-select fields`
  - `fd54a7d Add feature-based PDF alignment`

## Input Set

- Input directory: `inputs`
- PDF count: 56
- File naming pattern: `MX-M3658N_20260731_160125_001.pdf` through `MX-M3658N_20260731_160125_056.pdf`
- Expected scenario: normal fill batch, used as the baseline before weak-fill and abnormal-case testing.

## Active Recognition Configuration

Key configuration features in this baseline:

- PDF render: `pdf_dpi=144`, `pdf_page=1`
- Alignment: `FeatureBasedAlignment` with `inputs/reference.png`
- Single-choice weak mark fallback: enabled for `QTYPE_MCQ4`
- Template-level multi-select marking: `multiSelect=true` on multi-select field blocks
- Multi-select weak mark fallback: enabled for template-level multi-select fields
- Multi-select full-select fallback: enabled with adaptive page blank baseline
- Identifier weak fallback: enabled for `QTYPE_INT`, only when a digit is otherwise blank

The identifier fallback is intentionally separate from answer fallback because false-positive identifier recovery has higher operational risk.

## Command

```bash
python main.py -i inputs -o outputs_inputs_56_weak_identifier
```

## Output Artifacts

- Result CSV: `outputs_inputs_56_weak_identifier/Results/Results_03PM.csv`
- Checked OMR images: `outputs_inputs_56_weak_identifier/CheckedOMRs/`
- Run log: `weak_identifier_56.log`

## Result Summary

```text
rows 56
id_columns 8
q_columns 11
id_blank_cells 0
q_blank_cells 0
blank_rows 0
```

Interpretation:

- All 56 sheets were processed.
- All 448 identifier cells were recognized.
- All 616 answer cells were recognized.
- No row contains an empty identifier or answer field.

## Fallback Trigger Summary

```text
Weak identifier fallback: 1
Weak mark fallback: 0
Weak multi-mark fallback: 0
Weak multi full-select fallback: 2
```

Observed fallback events:

```text
Weak identifier fallback: field 'id8' -> '6'
Weak multi full-select fallback: field 'q10' -> 'ABCD'
Weak multi full-select fallback: field 'q11' -> 'ABCD'
```

The fallback volume is low and auditable. There was no broad triggering across the normal-fill batch.

## Delta Against Pre-identifier-fallback Run

Compared with `outputs_inputs_56_current_params/Results/Results_03PM.csv`, the final output changed only one cell:

```text
MX-M3658N_20260731_160125_005.png id8 '' -> '6'
```

The resulting identifier for that sheet is:

```text
MX-M3658N_20260731_160125_005.png id=25803716
```

All answer fields were unchanged by the identifier fallback.

## Multi-select Distribution Snapshot

The normal batch includes valid multi-select combinations, including all-option selections. This is important because later abnormal tests must not regress legal `ABCD` answers.

```text
q9  ABCD count: 7
q10 ABCD count: 1
q11 ABCD count: 8
```

The guarded full-select fallback triggered only twice, while other `ABCD` values were recognized by the normal thresholding path.

## Baseline Acceptance Criteria

Future weak-fill or abnormal-case changes should be compared against this baseline. For the normal-fill set, an acceptable result should satisfy:

1. `rows=56`
2. `id_blank_cells=0`
3. `q_blank_cells=0`
4. No answer-cell differences unless intentionally explained.
5. Fallback trigger counts remain small and inspectable.
6. Legal multi-select full selections such as `ABCD` remain supported.
7. If identifier fallback triggers, each event must be individually auditable in the log.

## Notes for Future Test Reports

For each later test batch, record:

- Input directory and file count.
- Branch and commit.
- Command and output directory.
- CSV summary: rows, blank identifier cells, blank answer cells, blank rows.
- Fallback trigger counts by type and field label.
- Cell-level diff against this baseline when the same sheets are reused.
- Manual confirmation screenshots or CheckedOMR paths for every unexpected fallback or blank field.
