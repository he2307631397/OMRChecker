# Alignment experiments for shifted PDF sheets

This document records the page alignment experiments for the 21 answer-sheet PDFs added on 2026-07-31.

## Problem

The original fixed-coordinate template worked for the first batch, but in the 21-sheet batch the later pages showed a visible offset between the red detection boxes and the actual exam-id bubbles. The failed rows mainly had blank `id1..id8` fields.

Baseline run:

```bash
python main.py -i inputs -o outputs_inputs_21_review
```

Baseline result summary from the repeated experiment:

| Case | Rows | Blank exam-id cells | Rows with blank exam-id | Blank question cells | Rows with any blank |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 21 | 78 | 10 | 8 | 11 |

## Experiments

To avoid changing `inputs/` during tests, copies were created under `alignment_experiments/` and each variant was written to a separate output directory.

| Case | Change | Output directory | Result |
| --- | --- | --- | --- |
| baseline | Same config as before alignment | `outputs_inputs_21_baseline/` | 78 blank exam-id cells |
| auto_align | `alignment_params.auto_align=true` | `outputs_inputs_21_auto_align/` | Slight improvement only, 74 blank exam-id cells |
| CropPage | `preProcessors=[CropPage]` | `outputs_inputs_21_crop_page/` | Failed for these PDFs: `Paper boundary not found` |
| FeatureBasedAlignment | ORB feature alignment to `reference.png` | `outputs_inputs_21_feature_align/` | Best result, 0 blank exam-id cells |

Summary CSV generated during the experiment:

```text
outputs_inputs_21_alignment_summary.csv
```

## Selected solution

Use OMRChecker's existing `FeatureBasedAlignment` preprocessor with a reference image rendered from the first sheet using the same 144 DPI PDF pipeline.

Final template configuration:

```json
"preProcessors": [
  {
    "name": "FeatureBasedAlignment",
    "options": {
      "reference": "reference.png",
      "maxFeatures": 2000,
      "goodMatchPercent": 0.25,
      "2d": true
    }
  }
]
```

The reference file is stored at:

```text
inputs/reference.png
```

Rationale:

- `FeatureBasedAlignment` directly corrects per-page translation and small affine shifts before fixed bubble coordinates are applied.
- It uses the existing project preprocessor mechanism, so no custom recognition code is needed.
- It improved the actual 21-sheet failure mode without broadening mark thresholds, reducing the risk of false positives.
- `CropPage` is not suitable for these rendered PDFs because no page boundary is detected.
- `auto_align` only performs field-level horizontal alignment and did not solve the page-level displacement.

## Final validation

Final run after applying the configuration to `inputs/template.json`:

```bash
python main.py -i inputs -o outputs_inputs_21_feature_final
```

Final result CSV:

```text
outputs_inputs_21_feature_final/Results/Results_12PM.csv
```

Feature-alignment-only summary:

| Rows | Blank exam-id cells | Rows with blank exam-id | Blank question cells | Rows with any blank |
| ---: | ---: | ---: | ---: | ---: |
| 21 | 0 | 0 | 1 | 1 |

The only remaining blank field after alignment alone was:

```text
MX-M3658N_20260731_123655_007.png: q10
```

This field was later confirmed to be a valid four-option multi-select (`ABCD`) and is covered by the guarded multi-select full-select fallback documented in `docs/weak-mark-detection.md`.

A visual comparison montage was generated for manual verification:

```text
outputs_inputs_21_feature_align/id_coord_compare/baseline_vs_feature_id_montage.png
```

## Notes and limitations

- The selected reference image is specific to this A4 template, PDF DPI, and current coordinate system.
- If future answer-sheet templates change, regenerate `inputs/reference.png` from a clean, correctly rendered sample of that template.
- This alignment step should remain separate from weak-mark fallback logic. Alignment fixes coordinate drift, while weak-mark fallback only handles truly light marks after the boxes are correctly placed.
- The final CSV was opened for manual review after the run.
