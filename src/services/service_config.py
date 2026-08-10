"""Service-level configuration for the Robyn OMR service."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ENV_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    workers: int = 0


@dataclass(frozen=True)
class StorageConfig:
    service_data_dir: Path = Path("service_data")
    template_dir: Path = Path("inputs")
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
    local_root: Path = Path("service_data/cos_mock")


@dataclass(frozen=True)
class CallbackConfig:
    url: str | None = None
    max_attempts: int = 3
    timeout_seconds: int = 10


@dataclass(frozen=True)
class RecognitionConfig:
    debug_artifacts: bool = False


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
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    archive_regions: list[ArchiveRegionConfig] = field(default_factory=list)


def load_service_config(path: str | Path | None = None) -> ServiceConfig:
    """Load service configuration from JSON and environment overrides."""
    _load_dotenv(Path(".env"))
    config_path = Path(path) if path is not None else Path("config/robyn-service.json")
    raw_config: dict[str, Any] = {}
    if config_path.exists():
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))

    resolved_config = _resolve_env_placeholders(raw_config)
    _apply_environment_overrides(resolved_config)

    server = resolved_config.get("server", {})
    storage = resolved_config.get("storage", {})
    database = resolved_config.get("database", {})
    cos = resolved_config.get("cos", {})
    callback = resolved_config.get("callback", {})
    recognition = resolved_config.get("recognition", {})

    return ServiceConfig(
        server=ServerConfig(
            host=str(server.get("host", ServerConfig.host)),
            port=int(server.get("port", ServerConfig.port)),
            workers=resolve_worker_count(server.get("workers", ServerConfig.workers)),
        ),
        storage=StorageConfig(
            service_data_dir=Path(storage.get("serviceDataDir", StorageConfig.service_data_dir)),
            template_dir=Path(storage.get("templateDir", StorageConfig.template_dir)),
            archive_prefix=str(storage.get("archivePrefix", StorageConfig.archive_prefix)),
        ),
        database=DatabaseConfig(
            url=str(database.get("url", DatabaseConfig.url)),
        ),
        cos=CosConfig(
            enabled=bool(cos.get("enabled", CosConfig.enabled)),
            region=str(cos.get("region", CosConfig.region)),
            bucket=str(cos.get("bucket", CosConfig.bucket)),
            secret_id=str(cos.get("secretId", CosConfig.secret_id)),
            secret_key=str(cos.get("secretKey", CosConfig.secret_key)),
            local_root=Path(cos.get("localRoot", CosConfig.local_root)),
        ),
        callback=CallbackConfig(
            url=_optional_http_url(callback.get("url"), "callback.url"),
            max_attempts=int(callback.get("maxAttempts", CallbackConfig.max_attempts)),
            timeout_seconds=int(callback.get("timeoutSeconds", CallbackConfig.timeout_seconds)),
        ),
        recognition=RecognitionConfig(
            debug_artifacts=_parse_bool(
                recognition.get("debugArtifacts", RecognitionConfig.debug_artifacts),
                "recognition.debugArtifacts",
            ),
        ),
        archive_regions=[
            ArchiveRegionConfig(
                region_code=str(region.get("regionCode", "")),
                region_name=str(region.get("regionName", "")),
                type=str(region.get("type", "")),
                bbox=list(region.get("bbox", [])),
            )
            for region in resolved_config.get("archiveRegions", [])
        ],
    )


def resolve_worker_count(value: Any = None) -> int:
    """Return a safe worker count for CPU-bound OMR/OCR recognition.

    ``0``, ``"auto"`` and omitted values mean auto-size from available CPUs.
    PaddleOCR already uses native compute threads, so the default is deliberately
    conservative to avoid oversubscribing production servers.
    """

    if value is None:
        requested = 0
    elif isinstance(value, str) and value.strip().lower() == "auto":
        requested = 0
    else:
        requested = int(value)
    if requested > 0:
        return requested

    cpu_count = os.cpu_count() or 1
    return max(1, min(4, cpu_count // 2 or 1))


def _resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, str):
        return _ENV_PLACEHOLDER_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    return value


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value_quotes(value.strip())


def _strip_env_value_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _apply_environment_overrides(config: dict[str, Any]) -> None:
    server = config.setdefault("server", {})
    storage = config.setdefault("storage", {})
    callback = config.setdefault("callback", {})
    recognition = config.setdefault("recognition", {})

    if "OMR_SERVICE_PORT" in os.environ:
        server["port"] = int(os.environ["OMR_SERVICE_PORT"])
    if "OMR_SERVICE_HOST" in os.environ:
        server["host"] = os.environ["OMR_SERVICE_HOST"]
    if "OMR_SERVICE_WORKERS" in os.environ:
        server["workers"] = os.environ["OMR_SERVICE_WORKERS"]
    if "OMR_SERVICE_DATA_DIR" in os.environ:
        storage["serviceDataDir"] = os.environ["OMR_SERVICE_DATA_DIR"]
    if "OMR_TEMPLATE_DIR" in os.environ:
        storage["templateDir"] = os.environ["OMR_TEMPLATE_DIR"]
    if "OMR_CALLBACK_URL" in os.environ:
        callback["url"] = os.environ["OMR_CALLBACK_URL"]
    if "OMR_RECOGNITION_DEBUG_ARTIFACTS" in os.environ:
        recognition["debugArtifacts"] = _parse_bool(
            os.environ["OMR_RECOGNITION_DEBUG_ARTIFACTS"],
            "OMR_RECOGNITION_DEBUG_ARTIFACTS",
        )


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


def _optional_non_empty_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_http_url(value: Any, field_name: str) -> str | None:
    url = _optional_non_empty_string(value, field_name)
    if url is None:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be a valid http:// or https:// URL")
    return url
