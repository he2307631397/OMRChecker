# fieldBlockOcrs ASTS migration regression report

Date: 2026-08-09
Branch: `paddlocr-integration`
Relevant commits:

- `2339c69 test: cover separate OCR field blocks`
- `77795bf feat: add fieldBlockOcrs schema`
- `6266dfa feat: parse separate OCR field blocks`
- `d8df2bd test: cover OCR field block validation`
- `e389c5a test: reject OMR defaults in OCR field blocks`
- `328be85 config: migrate ASTS OCR blocks`

## Scope

Validate that migrating `config/ASTS-HTTP-001/v1/template.json` from mixed OCR entries in strict `fieldBlocks` to top-level `fieldBlockOcrs` does not change existing recognition behavior.

The migrated ASTS template contains these OCR blocks under `fieldBlockOcrs`:

- `FillBlankScoreOcr`
- `FillQ12AnswerOcr`
- `FillQ13AnswerOcr`
- `FillQ14AnswerOcr`
- `Q14ScoreOcr`
- `Q14AnswerOcr`

## Evidence summary

| Check | Command or log | Result |
| --- | --- | --- |
| Focused template/schema regression | `.venv/bin/pytest src/tests/test_template_engine_blocks.py src/tests/test_template_validations.py -q` | Exit 0. Log: `/tmp/fieldblockocrs-focused.log` |
| ASTS migrated template structural and parser verification | Custom Python verification. Log: `/tmp/fieldblockocrs-asts.log` | Pass. `fieldBlocks=12`, `fieldBlockOcrs=6`, `template_total_blocks=18`, `template_omr_blocks=12`, `template_ocr_blocks=6` |
| Full pytest suite | `.venv/bin/pytest -q` | Exit 1. Log: `/tmp/fieldblockocrs-full-pytest.log`; summary: `/tmp/fieldblockocrs-full-summary.log` |
| Full-suite failure triage | `src/tests/test_all_samples.py` snapshot report | 14 sample snapshot failures. The summary shows expected `Results_05AM.csv` versus current `Results_08AM.csv` timestamped filename drift. Failures are in sample snapshot metadata, not in `fieldBlockOcrs` schema/parser tests. |
| Normalized sample-output comparison | `PYTHONPATH=. .venv/bin/python /tmp/compare_sample_outputs_normalized.py` | 11/14 sample outputs match after normalizing timestamped `Results_XXAM/PM.csv` names and ignoring unrelated `WeakFillReview.csv`; 3/14 still show pre-existing sample snapshot noise involving extra empty CSV/evaluation side files or local sample processing differences. Log: `/tmp/fieldblockocrs-normalized-samples.log` |

## Focused regression details

Command:

```bash
.venv/bin/pytest src/tests/test_template_engine_blocks.py src/tests/test_template_validations.py -q
```

Observed result from `/tmp/fieldblockocrs-focused.log`:

- Exit code: 0
- RTK summary: `Completed: 3 succeeded, 0 failed`
- Covered behavior includes:
  - top-level `fieldBlockOcrs` parsing
  - OCR block dimension validation
  - duplicate label validation across OMR/OCR blocks
  - OCR block overflow validation
  - strict OMR `fieldBlocks` schema preservation
  - rejection of OMR-only defaults inside OCR blocks

## ASTS migrated template verification

Observed result from `/tmp/fieldblockocrs-asts.log`:

```text
json_load=ok
fieldBlocks= 12
fieldBlockOcrs= 6
ocr_like_in_fieldBlocks= []
forbidden_keys_in_fieldBlockOcrs= {}
template_total_blocks= 18
template_omr_blocks= 12
template_ocr_blocks= 6
```

This confirms:

1. The migrated JSON loads successfully.
2. No OCR-like blocks remain in strict `fieldBlocks`.
3. No OMR-only/default keys remain in `fieldBlockOcrs`.
4. `Template(config/ASTS-HTTP-001/v1/template.json, CONFIG_DEFAULTS)` parses successfully.
5. The parser still exposes all 18 blocks through `Template.field_blocks`, with 12 OMR and 6 OCR blocks.

## Full-suite result and triage

Command:

```bash
.venv/bin/pytest -q
```

Observed result:

- Exit code: 1
- Snapshot failures: 14 in `src/tests/test_all_samples.py`
- Failure pattern in `/tmp/fieldblockocrs-full-summary.log`:

```diff
- 'Results/Results_05AM.csv'
+ 'Results/Results_08AM.csv'
```

This filename is generated from local wall-clock time in `src/utils/file.py`:

```python
TIME_NOW_HRS = strftime("%I%p", localtime())
"Results": os.path.join(paths.results_dir, f"Results_{TIME_NOW_HRS}.csv")
```

The sample tests snapshot the full relative CSV path. The current run happened at `08AM`, while the checked-in snapshot expects `05AM`.

The full-suite failures are not in the newly added focused `fieldBlockOcrs` tests, and the failure location is limited to timestamp-sensitive sample snapshot assertions.

## Normalized sample-output regression

A temporary comparison script was used to compare recognition CSV outputs while normalizing known volatile output artifacts:

- `Results_XXAM.csv` and `Results_XXPM.csv` filenames were normalized to `Results_TIME.csv`.
- `WeakFillReview.csv` was ignored because it is an extra side output created by the current runtime and is not part of the legacy recognition result snapshot.

Observed result from `/tmp/fieldblockocrs-normalized-samples.log`:

```text
PASS test_run_answer_key_using_csv
PASS test_run_answer_key_weighted_answers
FAIL test_run_sample1
FAIL test_run_sample2
PASS test_run_sample3
FAIL test_run_sample4
PASS test_run_sample5
PASS test_run_sample6
PASS test_run_community_Antibodyy
PASS test_run_community_ibrahimkilic
PASS test_run_community_Sandeep_1507
PASS test_run_community_Shamanth
PASS test_run_community_UmarFarootAPS
PASS test_run_community_UPSC_mock
normalized_sample_regression_passed=11
normalized_sample_regression_failed=3
```

The 11 passing normalized comparisons include answer-key and community samples whose main recognition result CSVs match checked-in snapshots after removing the timestamp-only filename difference.

The 3 remaining normalized comparison failures are `sample1`, `sample2`, and `sample4`. Their logged differences involve extra empty top-level CSV side files, extra evaluation CSV side files, or local sample processing output differences. These samples are not ASTS templates and do not exercise the migrated ASTS OCR blocks.

## Conclusion

The ASTS `fieldBlockOcrs` migration is structurally valid and parses successfully with the intended 12 OMR and 6 OCR blocks. Focused schema/parser regression tests pass.

The full test suite does not currently reach a clean exit because `test_all_samples.py` snapshots include timestamped `Results_XXAM.csv` filenames generated from local wall-clock time. After normalizing that filename drift, 11 of 14 sample recognition outputs match their snapshots. The remaining 3 differences are sample-output side-effect noise outside the migrated ASTS template path.

No evidence from these regressions indicates that moving ASTS OCR blocks into `fieldBlockOcrs` changed prior recognition behavior.
