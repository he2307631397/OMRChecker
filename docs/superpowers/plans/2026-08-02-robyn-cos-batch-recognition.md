# Robyn COS Batch Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add COS-backed exam batch recognition with persistent task records, business field passthrough, large-region artifact archiving, and terminal callbacks.

**Architecture:** Keep the existing single-file `/api/omr/tasks` flow intact. Add focused service modules for configuration, SQLite persistence, COS storage, batch orchestration, artifact generation, and callback payload rendering, then expose `/api/omr/batches` from Robyn.

**Tech Stack:** Python 3, Robyn, sqlite3 standard library, pytest, Tencent COS Python SDK when available, existing OMRChecker `run_omr_directory` wrapper.

---

## File Structure

- Create `config/robyn-service.example.json`
  - Example service-level config for server, storage, SQLite, COS, callback, and archive regions.
- Modify `.gitignore`
  - Ignore `config/robyn-service.json` and `service_data/*.db*` without touching unrelated entries.
- Create `src/services/service_config.py`
  - Load JSON config, resolve `${ENV_NAME}` placeholders, apply environment overrides, expose dataclasses.
- Create `src/tests/test_service_config.py`
  - Unit tests for config defaults, placeholder resolution, and environment overrides.
- Create `src/services/task_store.py`
  - SQLite schema creation and repository methods for batches, sheets, artifacts, callback attempts.
- Create `src/tests/test_task_store.py`
  - Repository tests using temporary SQLite files.
- Create `src/services/cos_client.py`
  - `CosDocumentClient` wrapper plus `LocalCosDocumentClient` fake for tests and development.
- Create `src/tests/test_cos_client.py`
  - Tests archive key generation and local fake download/upload behavior.
- Create `src/services/archive_regions.py`
  - Crop configured large regions from checked images and save local artifacts.
- Create `src/tests/test_archive_regions.py`
  - Image crop tests using generated test images.
- Create `src/services/batch_models.py`
  - Validation and normalization for external batch request payloads and camelCase response helpers.
- Create `src/tests/test_batch_models.py`
  - Request validation and response-shape tests.
- Create `src/services/batch_service.py`
  - Orchestrate COS download, OMR run, CSV row mapping, artifact upload, persistence updates, terminal payload creation.
- Create `src/tests/test_batch_service.py`
  - Orchestration tests with fake COS and fake OMR runner.
- Modify `web/robyn_app.py`
  - Load service config, keep existing task endpoints, add batch create/query endpoints, wire callback delivery for batch payloads.
- Create `src/tests/test_robyn_app_batches.py`
  - Robyn-layer tests for `/api/omr/batches` helpers without starting server.
- Modify `docs/robyn-web-service.md`
  - Add COS batch workflow and callback contract summary.
- Modify `README.md`
  - Keep short startup docs and link to detailed Robyn service doc.

---

## Task 1: Service Configuration

**Files:**
- Create: `config/robyn-service.example.json`
- Create: `src/services/service_config.py`
- Create: `src/tests/test_service_config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing config tests**

Create `src/tests/test_service_config.py`:

```python
import json
from pathlib import Path

from src.services.service_config import load_service_config


def test_load_service_config_resolves_env_placeholders(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_SECRET_ID", "sid")
    monkeypatch.setenv("COS_SECRET_KEY", "skey")
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text(json.dumps({
        "server": {"port": 8081, "workers": 2},
        "storage": {"serviceDataDir": "service_data", "templateDir": "inputs", "archivePrefix": "omr-archive"},
        "database": {"url": "sqlite:///service_data/omr_service.db"},
        "cos": {"enabled": True, "region": "ap-guangzhou", "bucket": "bucket", "secretId": "${COS_SECRET_ID}", "secretKey": "${COS_SECRET_KEY}"},
        "callback": {"maxAttempts": 3, "timeoutSeconds": 10},
        "archiveRegions": [{"regionCode": "singleChoice", "regionName": "单选题区域", "type": "SINGLE_CHOICE", "bbox": [1, 2, 30, 40]}]
    }), encoding="utf-8")

    config = load_service_config(config_path)

    assert config.server.port == 8081
    assert config.server.workers == 2
    assert config.cos.secret_id == "sid"
    assert config.cos.secret_key == "skey"
    assert config.archive_regions[0].bbox == [1, 2, 30, 40]


def test_load_service_config_allows_environment_port_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OMR_SERVICE_PORT", "9090")
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text("{}", encoding="utf-8")

    config = load_service_config(config_path)

    assert config.server.port == 9090
    assert config.storage.template_dir == Path("inputs")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest src/tests/test_service_config.py -q
```

Expected: FAIL because `src.services.service_config` does not exist.

- [ ] **Step 3: Implement service config**

Create `src/services/service_config.py`:

```python
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1


@dataclass(frozen=True)
class StorageConfig:
    service_data_dir: Path = Path("service_data")
    template_dir: Path = Path("inputs")
    task_retention_days: int = 30
    archive_prefix: str = "omr-archive"


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = "sqlite:///service_data/omr_service.db"


@dataclass(frozen=True)
class CosConfig:
    enabled: bool = False
    region: str = ""
    bucket: str = ""
    secret_id: str = ""
    secret_key: str = ""
    scheme: str = "https"
    download_timeout_seconds: int = 60
    upload_timeout_seconds: int = 60


@dataclass(frozen=True)
class CallbackConfig:
    max_attempts: int = 3
    timeout_seconds: int = 10
    signing_secret: str | None = None


@dataclass(frozen=True)
class ArchiveRegionConfig:
    region_code: str
    region_name: str
    type: str
    bbox: list[int]


@dataclass(frozen=True)
class ServiceConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    cos: CosConfig = field(default_factory=CosConfig)
    callback: CallbackConfig = field(default_factory=CallbackConfig)
    archive_regions: list[ArchiveRegionConfig] = field(default_factory=list)


def load_service_config(path: str | Path | None = None) -> ServiceConfig:
    data: dict[str, Any] = {}
    if path is not None and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    data = _resolve_env_placeholders(data)

    server = data.get("server", {})
    storage = data.get("storage", {})
    database = data.get("database", {})
    cos = data.get("cos", {})
    callback = data.get("callback", {})

    port = int(os.getenv("OMR_SERVICE_PORT", server.get("port", 8080)))
    workers = int(os.getenv("OMR_SERVICE_WORKERS", server.get("workers", 1)))

    return ServiceConfig(
        server=ServerConfig(host=server.get("host", "0.0.0.0"), port=port, workers=workers),
        storage=StorageConfig(
            service_data_dir=Path(os.getenv("OMR_SERVICE_DATA_DIR", storage.get("serviceDataDir", "service_data"))),
            template_dir=Path(os.getenv("OMR_TEMPLATE_DIR", storage.get("templateDir", "inputs"))),
            task_retention_days=int(storage.get("taskRetentionDays", 30)),
            archive_prefix=storage.get("archivePrefix", "omr-archive"),
        ),
        database=DatabaseConfig(url=database.get("url", "sqlite:///service_data/omr_service.db")),
        cos=CosConfig(
            enabled=bool(cos.get("enabled", False)),
            region=cos.get("region", ""),
            bucket=cos.get("bucket", ""),
            secret_id=cos.get("secretId", ""),
            secret_key=cos.get("secretKey", ""),
            scheme=cos.get("scheme", "https"),
            download_timeout_seconds=int(cos.get("downloadTimeoutSeconds", 60)),
            upload_timeout_seconds=int(cos.get("uploadTimeoutSeconds", 60)),
        ),
        callback=CallbackConfig(
            max_attempts=int(callback.get("maxAttempts", 3)),
            timeout_seconds=int(callback.get("timeoutSeconds", 10)),
            signing_secret=callback.get("signingSecret"),
        ),
        archive_regions=[
            ArchiveRegionConfig(
                region_code=item["regionCode"],
                region_name=item["regionName"],
                type=item["type"],
                bbox=list(item["bbox"]),
            )
            for item in data.get("archiveRegions", [])
        ],
    )


def _resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value)
        if match:
            return os.getenv(match.group(1), "")
    return value
```

Create `config/robyn-service.example.json` with the JSON from the approved spec, using `example-bucket-1250000000`.

Append to `.gitignore` if not already present:

```gitignore
config/robyn-service.json
service_data/*.db
service_data/*.db-*
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m pytest src/tests/test_service_config.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add config/robyn-service.example.json src/services/service_config.py src/tests/test_service_config.py .gitignore
git commit -m "feat: add robyn service configuration"
```

---

## Task 2: SQLite Task Store

**Files:**
- Create: `src/services/task_store.py`
- Create: `src/tests/test_task_store.py`

- [ ] **Step 1: Write failing task store tests**

Create `src/tests/test_task_store.py`:

```python
from src.services.task_store import TaskStore


def test_task_store_persists_batch_sheet_and_artifact(tmp_path):
    store = TaskStore.from_sqlite_path(tmp_path / "omr.db")
    store.initialize()

    store.create_batch({
        "batch_id": "batch-1",
        "exam_id": "exam-1",
        "external_batch_id": "ext-1",
        "callback_url": "https://example.com/callback",
        "recognition_config_json": "{}",
        "status": "queued",
        "created_at": "2026-08-02T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
    })
    store.create_sheet({
        "sheet_task_id": "sheet-task-1",
        "batch_id": "batch-1",
        "sheet_id": "sheet-1",
        "osskey": "omr/sheet-1.pdf",
        "status": "queued",
        "created_at": "2026-08-02T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
    })
    store.upsert_artifact({
        "artifact_id": "artifact-1",
        "batch_id": "batch-1",
        "sheet_id": "sheet-1",
        "artifact_type": "region_image",
        "region_code": "singleChoice",
        "region_name": "单选题区域",
        "region_type": "SINGLE_CHOICE",
        "bbox_json": "[1,2,3,4]",
        "local_path": "local.png",
        "osskey": "archive.png",
        "upload_status": "uploaded",
        "created_at": "2026-08-02T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
    })

    batch = store.get_batch("batch-1")
    sheets = store.list_sheets("batch-1")
    artifacts = store.list_artifacts("batch-1", "sheet-1")

    assert batch["exam_id"] == "exam-1"
    assert sheets[0]["sheet_id"] == "sheet-1"
    assert artifacts[0]["osskey"] == "archive.png"


def test_task_store_updates_status_and_records_callback_attempt(tmp_path):
    store = TaskStore.from_sqlite_path(tmp_path / "omr.db")
    store.initialize()
    now = "2026-08-02T00:00:00Z"
    store.create_batch({"batch_id": "batch-1", "exam_id": "exam-1", "status": "queued", "created_at": now, "updated_at": now})

    store.update_batch("batch-1", status="completed", completed_at=now, summary_json='{"total":1}')
    store.create_callback_attempt({
        "attempt_id": "attempt-1",
        "batch_id": "batch-1",
        "attempt_no": 1,
        "url": "https://example.com/callback",
        "status": "delivered",
        "http_status": 200,
        "created_at": now,
    })

    assert store.get_batch("batch-1")["status"] == "completed"
    assert store.list_callback_attempts("batch-1")[0]["status"] == "delivered"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_task_store.py -q
```

Expected: FAIL because `TaskStore` does not exist.

- [ ] **Step 3: Implement minimal SQLite repository**

Create `src/services/task_store.py` with schema creation and dict-based insert/update helpers. Use `sqlite3.Row` so repository methods return dictionaries. Include tables from the approved spec: `omr_batches`, `omr_batch_sheets`, `omr_artifacts`, `omr_callback_attempts`. Implement methods used by tests exactly: `from_sqlite_path`, `initialize`, `create_batch`, `create_sheet`, `upsert_artifact`, `get_batch`, `list_sheets`, `list_artifacts`, `update_batch`, `create_callback_attempt`, `list_callback_attempts`.

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest src/tests/test_task_store.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/task_store.py src/tests/test_task_store.py
git commit -m "feat: persist robyn batch task records"
```

---

## Task 3: COS Client Abstraction

**Files:**
- Create: `src/services/cos_client.py`
- Create: `src/tests/test_cos_client.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Write failing COS client tests**

Create `src/tests/test_cos_client.py`:

```python
from pathlib import Path

from src.services.cos_client import LocalCosDocumentClient, build_archive_osskey


def test_build_archive_osskey_uses_exam_batch_sheet_prefix():
    assert build_archive_osskey("omr-archive", "exam-1", "batch-1", "sheet-1", "regions/singleChoice.png") == "omr-archive/exam-1/batch-1/sheet-1/regions/singleChoice.png"


def test_local_cos_client_downloads_and_uploads_by_key(tmp_path):
    root = tmp_path / "cos"
    source = root / "input" / "sheet.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pdf")
    client = LocalCosDocumentClient(root)

    download_path = tmp_path / "downloaded.pdf"
    client.download_file("input/sheet.pdf", download_path)
    assert download_path.read_bytes() == b"pdf"

    upload_source = tmp_path / "region.png"
    upload_source.write_bytes(b"png")
    client.upload_file(upload_source, "archive/region.png")
    assert (root / "archive" / "region.png").read_bytes() == b"png"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_cos_client.py -q
```

Expected: FAIL because `cos_client` does not exist.

- [ ] **Step 3: Implement COS abstraction**

Create `src/services/cos_client.py` with:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class DocumentClient(Protocol):
    def download_file(self, osskey: str, local_path: Path) -> None: ...
    def upload_file(self, local_path: Path, osskey: str, content_type: str | None = None) -> None: ...


def build_archive_osskey(prefix: str, exam_id: str, batch_id: str, sheet_id: str, relative_path: str) -> str:
    parts = [prefix.strip("/"), exam_id.strip("/"), batch_id.strip("/"), sheet_id.strip("/"), relative_path.strip("/")]
    return "/".join(part for part in parts if part)


class LocalCosDocumentClient:
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)

    def download_file(self, osskey: str, local_path: Path) -> None:
        source = self.root_dir / osskey
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_path)

    def upload_file(self, local_path: Path, osskey: str, content_type: str | None = None) -> None:
        target = self.root_dir / osskey
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)


class CosDocumentClient:
    def __init__(self, config):
        from qcloud_cos import CosConfig, CosS3Client
        cos_config = CosConfig(Region=config.region, SecretId=config.secret_id, SecretKey=config.secret_key, Scheme=config.scheme)
        self.client = CosS3Client(cos_config)
        self.bucket = config.bucket

    def download_file(self, osskey: str, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        response = self.client.get_object(Bucket=self.bucket, Key=osskey)
        response["Body"].get_stream_to_file(str(local_path))

    def upload_file(self, local_path: Path, osskey: str, content_type: str | None = None) -> None:
        kwargs = {"Bucket": self.bucket, "Key": osskey, "LocalFilePath": str(local_path)}
        if content_type:
            kwargs["Headers"] = {"Content-Type": content_type}
        self.client.upload_file(**kwargs)
```

Add Tencent SDK dependency to `requirements.txt`:

```text
cos-python-sdk-v5
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest src/tests/test_cos_client.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/cos_client.py src/tests/test_cos_client.py requirements.txt
git commit -m "feat: add cos document client abstraction"
```

---

## Task 4: Batch Request Models and Payload Rendering

**Files:**
- Create: `src/services/batch_models.py`
- Create: `src/tests/test_batch_models.py`

- [ ] **Step 1: Write failing validation tests**

Create `src/tests/test_batch_models.py`:

```python
import pytest

from src.services.batch_models import parse_batch_request, render_batch_payload


def test_parse_batch_request_requires_exam_id_and_unique_sheets():
    request = parse_batch_request({
        "examId": " exam-1 ",
        "externalBatchId": " ext-1 ",
        "callbackUrl": "https://example.com/callback",
        "recognitionConfig": {"templateId": "default", "archiveRegionImages": True},
        "sheets": [
            {"sheetId": " sheet-1 ", "osskey": " input/sheet-1.pdf "},
            {"sheetId": "sheet-2", "osskey": "input/sheet-2.pdf"},
        ],
    })

    assert request.exam_id == "exam-1"
    assert request.sheets[0].sheet_id == "sheet-1"
    assert request.sheets[0].osskey == "input/sheet-1.pdf"


def test_parse_batch_request_rejects_duplicate_sheet_id():
    with pytest.raises(ValueError, match="duplicate sheetId"):
        parse_batch_request({"examId": "exam-1", "sheets": [{"sheetId": "s1", "osskey": "a.pdf"}, {"sheetId": "s1", "osskey": "b.pdf"}]})


def test_render_batch_payload_returns_business_fields_and_artifacts():
    payload = render_batch_payload(
        batch={"batch_id": "batch-1", "exam_id": "exam-1", "external_batch_id": "ext-1", "status": "completed", "created_at": "c", "completed_at": "d", "recognition_config_json": "{}"},
        sheets=[{"sheet_id": "sheet-1", "osskey": "input/sheet.pdf", "status": "completed", "recognition_status": "ACCEPTED", "exam_id_from_sheet": "23254519", "answers_json": '{"q1":"A"}', "items_json": "[]", "reviews_json": "[]", "checked_image_osskey": "archive/checked.png", "artifact_upload_status": "uploaded", "artifact_errors_json": "[]", "error": None}],
        artifacts=[{"sheet_id": "sheet-1", "artifact_type": "region_image", "region_code": "singleChoice", "region_name": "单选题区域", "region_type": "SINGLE_CHOICE", "osskey": "archive/region.png", "bbox_json": "[1,2,3,4]", "upload_status": "uploaded", "error": None}],
    )

    assert payload["schemaVersion"] == "omr-batch-result.v1"
    assert payload["examId"] == "exam-1"
    assert payload["sheets"][0]["sheetId"] == "sheet-1"
    assert payload["sheets"][0]["regionImages"][0]["osskey"] == "archive/region.png"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_batch_models.py -q
```

Expected: FAIL because `batch_models` does not exist.

- [ ] **Step 3: Implement validation and rendering**

Create `src/services/batch_models.py` with dataclasses `BatchSheetRequest`, `BatchRequest`, function `parse_batch_request(payload)`, and function `render_batch_payload(batch, sheets, artifacts)`. Use camelCase output exactly as in the tests. Parse JSON columns with `json.loads`, default missing JSON to `{}` or `[]`, and compute summary counts from sheet statuses.

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest src/tests/test_batch_models.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/batch_models.py src/tests/test_batch_models.py
git commit -m "feat: add robyn batch request models"
```

---

## Task 5: Large Region Artifact Generation

**Files:**
- Create: `src/services/archive_regions.py`
- Create: `src/tests/test_archive_regions.py`

- [ ] **Step 1: Write failing crop tests**

Create `src/tests/test_archive_regions.py`:

```python
from pathlib import Path

import cv2
import numpy as np

from src.services.archive_regions import crop_archive_regions
from src.services.service_config import ArchiveRegionConfig


def test_crop_archive_regions_writes_large_region_images(tmp_path):
    image_path = tmp_path / "checked.png"
    image = np.zeros((100, 120, 3), dtype=np.uint8)
    image[20:60, 10:50] = 255
    cv2.imwrite(str(image_path), image)

    artifacts = crop_archive_regions(
        checked_image_path=image_path,
        output_dir=tmp_path / "regions",
        regions=[ArchiveRegionConfig(region_code="candidateNumber", region_name="准考证号区域", type="CANDIDATE_NUMBER", bbox=[10, 20, 40, 40])],
    )

    assert artifacts[0].region_code == "candidateNumber"
    assert artifacts[0].local_path.exists()
    cropped = cv2.imread(str(artifacts[0].local_path))
    assert cropped.shape[:2] == (40, 40)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_archive_regions.py -q
```

Expected: FAIL because `archive_regions` does not exist.

- [ ] **Step 3: Implement crop helper**

Create `src/services/archive_regions.py` with an `ArchiveArtifact` dataclass and `crop_archive_regions(checked_image_path, output_dir, regions)`. Read with `cv2.imread`, clamp bbox to image bounds, write `{region_code}.png`, and return artifact metadata.

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest src/tests/test_archive_regions.py -q
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/archive_regions.py src/tests/test_archive_regions.py
git commit -m "feat: generate large review region artifacts"
```

---

## Task 6: Batch Service Orchestration

**Files:**
- Create: `src/services/batch_service.py`
- Create: `src/tests/test_batch_service.py`

- [ ] **Step 1: Write failing orchestration tests**

Create `src/tests/test_batch_service.py` with a fake document client and fake OMR runner. Test that creating a batch downloads `sheetId.pdf`, persists completed sheet results, creates artifact osskeys, and returns terminal payload with `examId`, `sheetId`, `osskey`, `answers`, and `regionImages`.

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_batch_service.py -q
```

Expected: FAIL because `batch_service` does not exist.

- [ ] **Step 3: Implement batch orchestration**

Create `src/services/batch_service.py` with `BatchService`. Constructor accepts `config`, `store`, `document_client`, and optional `omr_runner`. Implement:

- `create_batch(request_payload) -> dict`
- `run_batch(batch_id) -> dict`
- `_download_sheets`
- `_run_omr`
- `_map_rows_to_sheets`
- `_create_and_upload_artifacts`
- `get_batch_payload(batch_id) -> dict`

Use file naming `{sheetId}{original_extension}` for downloads so CSV `input_path` can be mapped back to sheet.

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest src/tests/test_batch_service.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/batch_service.py src/tests/test_batch_service.py
git commit -m "feat: orchestrate cos batch recognition"
```

---

## Task 7: Robyn Batch Endpoints and Callback Wiring

**Files:**
- Modify: `web/robyn_app.py`
- Create: `src/tests/test_robyn_app_batches.py`

- [ ] **Step 1: Write failing Robyn helper tests**

Create tests for helper functions that parse request JSON, call `BatchService.create_batch`, store the future, query payloads, and deliver terminal callbacks. Do not start a real Robyn server.

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest src/tests/test_robyn_app_batches.py -q
```

Expected: FAIL because batch endpoint helpers do not exist.

- [ ] **Step 3: Modify Robyn app**

Add:

- CLI config path parsing in `if __name__ == "__main__"`.
- Global service config initialization.
- `POST /api/omr/batches`.
- `GET /api/omr/batches`.
- `GET /api/omr/batches/:batch_id`.
- `GET /api/omr/batches/:batch_id/checked-image/:sheet_id`.
- Batch terminal callback delivery using existing `_post_callback`, configured retry count, and persisted attempts.

Keep existing `/api/omr/tasks` behavior unchanged.

- [ ] **Step 4: Run focused tests**

```bash
python -m pytest src/tests/test_robyn_app_batches.py src/tests/test_robyn_app_task_records.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/robyn_app.py src/tests/test_robyn_app_batches.py
git commit -m "feat: expose robyn cos batch endpoints"
```

---

## Task 8: Documentation and End-to-End Verification

**Files:**
- Modify: `docs/robyn-web-service.md`
- Modify: `README.md`

- [ ] **Step 1: Update docs**

Add a COS batch section to `docs/robyn-web-service.md` with startup config, `/api/omr/batches` request, callback response, query examples, and region artifact explanation. Keep README concise and link to the detailed doc.

- [ ] **Step 2: Run full focused suite**

```bash
python -m pytest \
  src/tests/test_service_config.py \
  src/tests/test_task_store.py \
  src/tests/test_cos_client.py \
  src/tests/test_batch_models.py \
  src/tests/test_archive_regions.py \
  src/tests/test_batch_service.py \
  src/tests/test_robyn_app_batches.py \
  src/tests/test_robyn_app_task_records.py \
  -q
```

Expected: all pass.

- [ ] **Step 3: Run a local fake-COS smoke test**

Use `LocalCosDocumentClient` with a local source directory containing a known PDF, submit a batch with one sheet, and verify the terminal payload has:

- `examId`
- `sheets[0].sheetId`
- `sheets[0].osskey`
- `sheets[0].answers`
- `sheets[0].regionImages`
- `sheets[0].checkedImageOsskey`

- [ ] **Step 4: Commit docs and verification fixes**

```bash
git add docs/robyn-web-service.md README.md
git commit -m "docs: document robyn cos batch workflow"
```

---

## Self-Review

Spec coverage:

- Service config file: Task 1.
- COS client download/upload: Task 3.
- `/api/omr/batches`: Task 7.
- `examId + sheets[{sheetId, osskey}]`: Task 4 and Task 7.
- `recognitionConfig` passthrough: Task 4 and Task 6.
- SQLite persistence: Task 2 and Task 6.
- Large-region screenshots: Task 5 and Task 6.
- Async artifact upload: Task 6, implemented behind batch service with fakeable document client.
- Callback payload and compensation query: Task 4, Task 6, Task 7.
- Docs: Task 8.

Placeholder scan: This plan contains no unresolved placeholder markers. Any implementation that needs production COS credentials must use `config/robyn-service.json` or environment variables, not committed code.

Type consistency: External JSON uses camelCase. Internal SQLite columns use snake_case. Conversion is centralized in `batch_models.render_batch_payload`.
