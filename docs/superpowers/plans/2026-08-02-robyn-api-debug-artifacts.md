# Robyn API Debug Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Robyn API-only `debugArtifacts` switch so production interface calls return JSON without retaining local process files, while CLI/local debugging output remains unchanged.

**Architecture:** Add a `RecognitionConfig` to service configuration and a request-level `recognitionConfig.debugArtifacts` override to batch requests. `BatchRecognitionService` resolves the effective value per batch, runs recognition normally, uploads business artifacts before cleanup, then deletes only Robyn-created sheet workdirs when preservation is disabled.

**Tech Stack:** Python dataclasses, pytest, Robyn service modules, existing `TaskStore`, existing fake COS test helpers.

---

## File structure

- Modify `src/services/service_config.py`
  - Add `RecognitionConfig(debug_artifacts: bool = False)`.
  - Load `recognition.debugArtifacts` from JSON.
  - Add env override `OMR_RECOGNITION_DEBUG_ARTIFACTS` with strict boolean parsing.

- Modify `src/services/batch_models.py`
  - Add request model field `debug_artifacts: bool | None = None` to `BatchRecognitionRequest`.
  - Parse optional `recognitionConfig.debugArtifacts` from API JSON.
  - Serialize it back through `to_api_dict()` only when not `None`.
  - Reject non-boolean values.

- Modify `src/services/batch_service.py`
  - Resolve effective debug artifact preservation from request override or service config.
  - Track created sheet workdirs during `process_batch`.
  - After result persistence and callback preparation, clean those workdirs when disabled.
  - Cleanup failures are non-fatal and added to sheet result metadata as `artifactCleanupError`.

- Modify tests:
  - `src/tests/test_service_config.py`
  - `src/tests/test_batch_models.py`
  - `src/tests/test_batch_service.py`
  - `src/tests/test_omr_service.py` if present, otherwise add regression coverage in the closest existing OMR service test file.

---

### Task 1: Service config support

**Files:**
- Modify: `src/services/service_config.py`
- Test: `src/tests/test_service_config.py`

- [ ] **Step 1: Write failing tests for default, JSON config, env override, and invalid env**

Add tests like this to `src/tests/test_service_config.py`:

```python
def test_recognition_debug_artifacts_defaults_to_false(tmp_path, monkeypatch):
    monkeypatch.delenv("OMR_RECOGNITION_DEBUG_ARTIFACTS", raising=False)
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text("{}", encoding="utf-8")

    config = load_service_config(config_path)

    assert config.recognition.debug_artifacts is False


def test_recognition_debug_artifacts_loads_from_json(tmp_path, monkeypatch):
    monkeypatch.delenv("OMR_RECOGNITION_DEBUG_ARTIFACTS", raising=False)
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"recognition": {"debugArtifacts": true}}', encoding="utf-8")

    config = load_service_config(config_path)

    assert config.recognition.debug_artifacts is True


def test_recognition_debug_artifacts_env_overrides_json(tmp_path, monkeypatch):
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"recognition": {"debugArtifacts": false}}', encoding="utf-8")
    monkeypatch.setenv("OMR_RECOGNITION_DEBUG_ARTIFACTS", "yes")

    config = load_service_config(config_path)

    assert config.recognition.debug_artifacts is True


def test_recognition_debug_artifacts_invalid_env_value_fails(tmp_path, monkeypatch):
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OMR_RECOGNITION_DEBUG_ARTIFACTS", "sometimes")

    with pytest.raises(ValueError, match="OMR_RECOGNITION_DEBUG_ARTIFACTS"):
        load_service_config(config_path)
```

If the file does not already import `pytest`, add `import pytest`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_service_config.py -q
```

Expected: fails because `ServiceConfig` has no `recognition` field or env parsing.

- [ ] **Step 3: Implement config support**

In `src/services/service_config.py`, add:

```python
@dataclass(frozen=True)
class RecognitionConfig:
    debug_artifacts: bool = False
```

Add this field to `ServiceConfig`:

```python
recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
```

Inside `load_service_config`, read the section:

```python
recognition = resolved_config.get("recognition", {})
```

Pass it into `ServiceConfig`:

```python
recognition=RecognitionConfig(
    debug_artifacts=_parse_bool(
        recognition.get("debugArtifacts", RecognitionConfig.debug_artifacts),
        "recognition.debugArtifacts",
    ),
),
```

Add helper near the bottom:

```python
def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be a boolean")
```

Update `_apply_environment_overrides`:

```python
recognition = config.setdefault("recognition", {})
if "OMR_RECOGNITION_DEBUG_ARTIFACTS" in os.environ:
    recognition["debugArtifacts"] = _parse_bool(
        os.environ["OMR_RECOGNITION_DEBUG_ARTIFACTS"],
        "OMR_RECOGNITION_DEBUG_ARTIFACTS",
    )
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_service_config.py -q
```

Expected: all service config tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/service_config.py src/tests/test_service_config.py
git commit -m "feat: add robyn recognition debug config"
```

---

### Task 2: Batch request override model

**Files:**
- Modify: `src/services/batch_models.py`
- Test: `src/tests/test_batch_models.py`

- [ ] **Step 1: Write failing tests**

Add tests to `src/tests/test_batch_models.py`:

```python
def test_batch_request_debug_artifacts_override_parses_true():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "recognitionConfig": {"debugArtifacts": True},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is True
    assert request.to_api_dict()["recognitionConfig"] == {"debugArtifacts": True}


def test_batch_request_debug_artifacts_override_parses_false():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "recognitionConfig": {"debugArtifacts": False},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is False
    assert request.to_api_dict()["recognitionConfig"] == {"debugArtifacts": False}


def test_batch_request_omits_recognition_config_when_no_override():
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )

    assert request.debug_artifacts is None
    assert "recognitionConfig" not in request.to_api_dict()


def test_batch_request_rejects_non_boolean_debug_artifacts():
    with pytest.raises(ValueError, match="recognitionConfig.debugArtifacts"):
        BatchRecognitionRequest.from_api_json(
            {
                "examId": "exam-001",
                "recognitionConfig": {"debugArtifacts": "true"},
                "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
            }
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_batch_models.py -q
```

Expected: fails because `debug_artifacts` is not implemented.

- [ ] **Step 3: Implement request parsing and serialization**

In `BatchRecognitionRequest`, add field:

```python
debug_artifacts: bool | None = None
```

Inside `from_api_json`, parse:

```python
recognition_config = payload.get("recognitionConfig") or {}
if not isinstance(recognition_config, dict):
    raise ValueError("recognitionConfig must be an object")
debug_artifacts = recognition_config.get("debugArtifacts")
if debug_artifacts is not None and not isinstance(debug_artifacts, bool):
    raise ValueError("recognitionConfig.debugArtifacts must be a boolean")
```

Pass `debug_artifacts=debug_artifacts` to the dataclass constructor.

Inside `to_api_dict`, add:

```python
if self.debug_artifacts is not None:
    payload["recognitionConfig"] = {"debugArtifacts": self.debug_artifacts}
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_batch_models.py -q
```

Expected: all batch model tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/batch_models.py src/tests/test_batch_models.py
git commit -m "feat: allow batch debug artifact override"
```

---

### Task 3: Batch service cleanup behavior

**Files:**
- Modify: `src/services/batch_service.py`
- Test: `src/tests/test_batch_service.py`

- [ ] **Step 1: Write failing tests for default cleanup and preserve override**

Add helper recognition runners in `src/tests/test_batch_service.py` if not already present:

```python
def runner_that_writes_process_files(context):
    context.workdir.mkdir(parents=True, exist_ok=True)
    source_dir = context.workdir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    output_dir = context.workdir / "output" / "CheckedOMRs"
    output_dir.mkdir(parents=True, exist_ok=True)
    checked_image = output_dir / f"{context.sheet.sheet_id}.png"
    checked_image.write_bytes(b"checked")
    process_file = context.workdir / "output" / "process-debug.txt"
    process_file.write_text("debug", encoding="utf-8")
    return RecognitionOutput(
        result={"answers": {"Q1": "A"}, "checkedImagePath": str(checked_image)},
        checked_image_path=checked_image,
    )
```

Add tests:

```python
def test_process_batch_cleans_sheet_workdirs_by_default(tmp_path):
    service, store, storage = make_batch_service(
        tmp_path,
        recognition_runner=runner_that_writes_process_files,
    )
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )
    storage.put_object("incoming/sheet-1.png", b"image")
    submitted = service.submit_batch(request)

    result = service.process_batch(submitted.task_id)

    assert result.status == "completed"
    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert not sheet_workdir.exists()
    assert result.sheets[0].result["checkedImageOsskey"].startswith("checked/")


def test_process_batch_preserves_sheet_workdirs_when_request_debug_artifacts_true(tmp_path):
    service, store, storage = make_batch_service(
        tmp_path,
        recognition_runner=runner_that_writes_process_files,
    )
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "recognitionConfig": {"debugArtifacts": True},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )
    storage.put_object("incoming/sheet-1.png", b"image")
    submitted = service.submit_batch(request)

    result = service.process_batch(submitted.task_id)

    assert result.status == "completed"
    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert (sheet_workdir / "output" / "process-debug.txt").exists()
```

- [ ] **Step 2: Write failing test for service config true overridden by request false**

```python
def test_process_batch_request_false_cleans_when_service_config_preserves(tmp_path):
    config = make_service_config(tmp_path, debug_artifacts=True)
    service, store, storage = make_batch_service(
        tmp_path,
        config=config,
        recognition_runner=runner_that_writes_process_files,
    )
    request = BatchRecognitionRequest.from_api_json(
        {
            "examId": "exam-001",
            "recognitionConfig": {"debugArtifacts": False},
            "sheets": [{"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}],
        }
    )
    storage.put_object("incoming/sheet-1.png", b"image")
    submitted = service.submit_batch(request)

    service.process_batch(submitted.task_id)

    sheet_workdir = tmp_path / "service_data" / "tasks" / submitted.task_id / "sheets" / "sheet-1"
    assert not sheet_workdir.exists()
```

If `make_service_config` does not accept `debug_artifacts`, update it in the implementation step.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_batch_service.py -q
```

Expected: tests fail because workdirs are still preserved and config helper lacks `debug_artifacts`.

- [ ] **Step 4: Implement cleanup and effective config**

In `BatchRecognitionService`, add methods:

```python
def _should_preserve_debug_artifacts(self, request: BatchRecognitionRequest) -> bool:
    if request.debug_artifacts is not None:
        return request.debug_artifacts
    return self.config.recognition.debug_artifacts


def _cleanup_sheet_workdirs(self, task_id: str, sheet_workdirs: dict[str, Path]) -> bool:
    cleanup_errors = False
    for sheet_id, workdir in sheet_workdirs.items():
        try:
            shutil.rmtree(workdir)
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 - cleanup must not fail recognition.
            cleanup_errors = True
            sheet = self.store.get_sheet(task_id, sheet_id)
            result_json = dict(sheet.get("result_json") or {}) if sheet else {}
            result_json["artifactCleanupError"] = str(exc)
            self.store.update_sheet(
                task_id=task_id,
                sheet_id=sheet_id,
                source_osskey=sheet["source_osskey"] if sheet else "",
                status=sheet["status"] if sheet else "completed",
                result_json=result_json,
                error=sheet.get("error") if sheet else None,
            )
    return cleanup_errors
```

At the start of `process_batch`, after parsing request, add:

```python
preserve_debug_artifacts = self._should_preserve_debug_artifacts(request)
sheet_workdirs: dict[str, Path] = {}
```

After creating each `workdir`, add:

```python
sheet_workdirs[sheet_request.sheet_id] = workdir
```

After computing and storing the terminal result, but before callback, run cleanup if disabled:

```python
if not preserve_debug_artifacts:
    cleanup_errors = self._cleanup_sheet_workdirs(task_id, sheet_workdirs)
    if cleanup_errors:
        status = self._compute_batch_status(task_id, artifact_errors=True)
        result = self._result_from_store(task_id, status=status)
        self.store.update_batch_status(task_id, status, result_json=result.to_callback_dict())
```

Then load `final_result = self._result_from_store(task_id)` and send callback.

If `TaskStore` has no `get_sheet`, use `next((s for s in self.store.list_sheets(task_id) if s["sheet_id"] == sheet_id), None)`.

- [ ] **Step 5: Update test config helper**

If `src/tests/test_batch_service.py` has a helper like `make_service_config`, update it to accept debug artifacts:

```python
def make_service_config(tmp_path, *, debug_artifacts=False, archive_regions=None):
    return ServiceConfig(
        storage=StorageConfig(
            service_data_dir=tmp_path / "service_data",
            template_dir=tmp_path / "templates",
        ),
        cos=CosConfig(enabled=True, local_root=tmp_path / "cos"),
        recognition=RecognitionConfig(debug_artifacts=debug_artifacts),
        archive_regions=archive_regions or [],
    )
```

Import `RecognitionConfig` from `src.services.service_config`.

- [ ] **Step 6: Run GREEN**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_batch_service.py -q
```

Expected: all batch service tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/services/batch_service.py src/tests/test_batch_service.py
git commit -m "feat: clean robyn batch artifacts by default"
```

---

### Task 4: CLI/local behavior regression guard

**Files:**
- Test: `src/tests/test_omr_service.py` or existing OMR service test file
- Modify only if a helper import is needed.

- [ ] **Step 1: Locate OMR service tests**

Run:

```bash
find src/tests -name '*omr*service*' -o -name 'test_omr*.py'
```

Use an existing file if present. If none exists, create `src/tests/test_omr_service.py`.

- [ ] **Step 2: Write regression test that `run_omr_directory` does not clean its output directory**

Use monkeypatch to avoid full OMR execution and assert the service wrapper preserves output files:

```python
from pathlib import Path

from src.services import omr_service


def test_run_omr_directory_preserves_output_directory(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    def fake_entry_point(root_dir, args):
        results_dir = Path(args["output_dir"]) / "Results"
        checked_dir = Path(args["output_dir"]) / "CheckedOMRs"
        results_dir.mkdir(parents=True)
        checked_dir.mkdir(parents=True)
        (results_dir / "Results_001.csv").write_text(
            "file_id,input_path,output_path,score\n"
            "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,1\n",
            encoding="utf-8",
        )
        (checked_dir / "sheet-1.png").write_bytes(b"checked")

    monkeypatch.setattr(omr_service, "entry_point", fake_entry_point)

    result = omr_service.run_omr_directory(input_dir, output_dir)

    assert result.count == 1
    assert (output_dir / "Results" / "Results_001.csv").exists()
    assert (output_dir / "CheckedOMRs" / "sheet-1.png").exists()
```

- [ ] **Step 3: Run test**

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest src/tests/test_omr_service.py -q
```

Expected: PASS. If import paths differ, adjust only the import path, not production behavior.

- [ ] **Step 4: Commit**

```bash
git add src/tests/test_omr_service.py
git commit -m "test: guard omr service output preservation"
```

---

### Task 5: Documentation and final verification

**Files:**
- Modify: `docs/robyn-web-service.md`
- Modify: `README.md` only if current README has a Robyn config bullet that should mention debug artifacts.

- [ ] **Step 1: Update Robyn service docs**

Add to `docs/robyn-web-service.md` near the COS batch config section:

```markdown
### Debug artifacts

Robyn API calls default to returning JSON recognition results without retaining local per-sheet process files. This keeps production service storage small and avoids exposing intermediate debugging artifacts as part of normal interface behavior.

Enable local process-file retention only when troubleshooting recognition quality:

```json
{
  "recognition": {
    "debugArtifacts": true
  }
}
```

For a single batch, override the service default in the request:

```json
{
  "examId": "exam-001",
  "recognitionConfig": {"debugArtifacts": true},
  "sheets": [
    {"sheetId": "sheet-1", "osskey": "incoming/sheet-1.png"}
  ]
}
```

This switch only applies to Robyn service work directories. CLI runs through `main.py` still write their normal `Results`, `CheckedOMRs`, and related debugging outputs.
```

- [ ] **Step 2: Run focused tests and syntax check**

Run:

```bash
../robyn-callback-task-records/.venv/bin/python -m pytest \
  src/tests/test_service_config.py \
  src/tests/test_batch_models.py \
  src/tests/test_batch_service.py \
  src/tests/test_omr_service.py \
  src/tests/test_robyn_app_batch_endpoints.py -q

../robyn-callback-task-records/.venv/bin/python -m py_compile \
  src/services/service_config.py \
  src/services/batch_models.py \
  src/services/batch_service.py \
  src/services/omr_service.py \
  web/robyn_app.py
```

Expected: pytest exits 0 and py_compile exits 0.

- [ ] **Step 3: Check git diff and status**

Run:

```bash
rtk git diff --stat
rtk git status --short
```

Expected: only intended files changed.

- [ ] **Step 4: Commit docs and any remaining verification changes**

```bash
git add docs/robyn-web-service.md README.md
git commit -m "docs: document robyn debug artifact toggle"
```

If README was not changed, omit it from `git add`.

- [ ] **Step 5: Final post-commit verification**

Run:

```bash
rtk git status --short
rtk git log --oneline -5
```

Expected: clean status and latest commits include the debug artifact implementation commits.

---

## Self-review against spec

- Service config default, JSON config, env override, and invalid env are covered by Task 1.
- Request-level override is covered by Task 2 and Task 3.
- Default Robyn cleanup and preservation behavior are covered by Task 3.
- Cleanup failure non-fatal behavior is specified in Task 3 implementation. If direct failure injection is practical, add a test by monkeypatching `shutil.rmtree` to raise `OSError("permission denied")` and assert `artifactCleanupError` appears in sheet result.
- CLI/local behavior unchanged is covered by Task 4.
- Documentation is covered by Task 5.
- No placeholders remain. Type names are consistent: `debug_artifacts`, `debugArtifacts`, `RecognitionConfig`.
