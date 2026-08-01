# Weak-fill 10-sheet Test Report

## Purpose

This document records the first weak-fill batch tested after the normal-fill 56-sheet baseline. It is used to identify which recognition paths still fail under light marking and to guide the next optimization step.

## Branch and Version

- Branch: `robyn-web-service`
- Baseline document: `docs/normal-fill-56-baseline.md`
- Current relevant commit before this test:
  - `f6946e7 Document normal-fill 56-sheet baseline`
  - `feb48dd Add weak identifier fallback detection`
  - `f82463f Merge branch 'alignment-experiments' into robyn-web-service`

## Input Set

- Input directory: `inputs`
- PDF count: 10
- File naming pattern: `MX-M3658N_20260731_162311_001.pdf` through `MX-M3658N_20260731_162311_010.pdf`
- Scenario: weak-fill answer sheets.

## Command

```bash
python main.py -i inputs -o outputs_inputs_10_weak_fill
```

## Output Artifacts

- Result CSV: `outputs_inputs_10_weak_fill/Results/Results_03PM.csv`
- Checked OMR images: `outputs_inputs_10_weak_fill/CheckedOMRs/`
- Run log: `weak_fill_10.log`

## Result Summary

```text
rows 10
id_blank_cells 12
q_blank_cells 3
blank_cells 15
blank_rows 6
```

Blank fields:

```text
MX-M3658N_20260731_162311_001.png id7
MX-M3658N_20260731_162311_001.png q5
MX-M3658N_20260731_162311_002.png id1
MX-M3658N_20260731_162311_002.png id2
MX-M3658N_20260731_162311_002.png id3
MX-M3658N_20260731_162311_002.png id5
MX-M3658N_20260731_162311_002.png id6
MX-M3658N_20260731_162311_002.png id7
MX-M3658N_20260731_162311_003.png id2
MX-M3658N_20260731_162311_003.png id7
MX-M3658N_20260731_162311_004.png id5
MX-M3658N_20260731_162311_004.png id6
MX-M3658N_20260731_162311_004.png id7
MX-M3658N_20260731_162311_008.png q3
MX-M3658N_20260731_162311_009.png q6
```

## Fallback Trigger Summary

```text
Weak identifier fallback: 0
Weak mark fallback: 0
Weak multi-mark fallback: 0
Weak multi full-select fallback: 0
```

Interpretation: the current guarded fallbacks are still too conservative for this weak-fill batch, and none of them triggered.

## Candidate Statistics for Blank Fields

```text
MX-M3658N_20260731_162311_001.png id7 darkest=1 mean=205.65 gap=15.24 delta_from_blank=18.54
MX-M3658N_20260731_162311_001.png q5  darkest=A mean=209.01 gap=25.64 delta_from_blank=45.99
MX-M3658N_20260731_162311_002.png id1 darkest=2 mean=201.39 gap=15.37 delta_from_blank=19.64
MX-M3658N_20260731_162311_002.png id2 darkest=4 mean=203.98 gap=13.97 delta_from_blank=17.62
MX-M3658N_20260731_162311_002.png id3 darkest=3 mean=206.15 gap=11.39 delta_from_blank=15.86
MX-M3658N_20260731_162311_002.png id5 darkest=1 mean=205.07 gap=14.51 delta_from_blank=18.30
MX-M3658N_20260731_162311_002.png id6 darkest=0 mean=208.77 gap=12.48 delta_from_blank=16.81
MX-M3658N_20260731_162311_002.png id7 darkest=7 mean=202.93 gap=18.80 delta_from_blank=22.33
MX-M3658N_20260731_162311_003.png id2 darkest=3 mean=200.64 gap=16.77 delta_from_blank=20.77
MX-M3658N_20260731_162311_003.png id7 darkest=1 mean=206.14 gap=15.80 delta_from_blank=17.39
MX-M3658N_20260731_162311_004.png id5 darkest=4 mean=204.04 gap=15.20 delta_from_blank=19.37
MX-M3658N_20260731_162311_004.png id6 darkest=8 mean=201.00 gap=19.14 delta_from_blank=23.15
MX-M3658N_20260731_162311_004.png id7 darkest=4 mean=209.67 gap=11.56 delta_from_blank=14.69
MX-M3658N_20260731_162311_008.png q3  darkest=A mean=205.15 gap=10.61 delta_from_blank=39.23
MX-M3658N_20260731_162311_009.png q6  darkest=D mean=158.74 gap=49.36 delta_from_blank=75.93
```

## Initial Findings

- The three blank answer fields have clear darkest candidates.
- `q6` on sheet 009 is especially strong and should be recoverable safely.
- `q5` on sheet 001 is also clear by local blank baseline.
- `q3` on sheet 008 is weaker but still has a darkest candidate with a clear page/question-local contrast.
- Identifier blanks are substantially lighter than the normal-fill batch, but most still show a consistent darkest candidate.
- Current identifier fallback thresholds `min_gap=20`, `min_delta_from_blank=25`, and `max_mean=205` are too strict for these weak-fill identifiers.
- Current answer weak fallback did not trigger, so the next step should inspect whether its field-direction guard is excluding the current template layout before relaxing thresholds.

## Recommended Next Step

Do not broadly lower the normal threshold. Instead, optimize the fallback layer:

1. Keep the normal-fill 56-sheet report as the non-regression baseline.
2. Fix or generalize answer weak fallback so it applies to the current `QTYPE_MCQ4` template orientation.
3. Add a weak-fill mode for identifier fallback with page/question-local contrast as the primary signal and absolute mean as a secondary cap.
4. Re-run both:
   - normal-fill 56-sheet baseline, requiring no broad new false positives
   - weak-fill 10-sheet batch, requiring fewer or zero blank fields
5. Record every fallback trigger in the log and in the next test report.
