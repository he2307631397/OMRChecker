"""Service-level configuration for the Robyn OMR service."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ENV_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class ServerConfig:
    port: int = 8080
    workers: int = 1


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


@dataclass(frozen=True)
class CallbackConfig:
    max_attempts: int = 3
    timeout_seconds: int = 10


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
    """Load service configuration from JSON and environment overrides."""
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

    return ServiceConfig(
        server=ServerConfig(
            port=int(server.get("port", ServerConfig.port)),
            workers=int(server.get("workers", ServerConfig.workers)),
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
        ),
        callback=CallbackConfig(
            max_attempts=int(callback.get("maxAttempts", CallbackConfig.max_attempts)),
            timeout_seconds=int(callback.get("timeoutSeconds", CallbackConfig.timeout_seconds)),
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


def _resolve_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, str):
        return _ENV_PLACEHOLDER_PATTERN.sub(lambda match: os.environ.get(match.group(1), ""), value)
    return value


def _apply_environment_overrides(config: dict[str, Any]) -> None:
    server = config.setdefault("server", {})
    storage = config.setdefault("storage", {})

    if "OMR_SERVICE_PORT" in os.environ:
        server["port"] = int(os.environ["OMR_SERVICE_PORT"])
    if "OMR_SERVICE_WORKERS" in os.environ:
        server["workers"] = int(os.environ["OMR_SERVICE_WORKERS"])
    if "OMR_SERVICE_DATA_DIR" in os.environ:
        storage["serviceDataDir"] = os.environ["OMR_SERVICE_DATA_DIR"]
    if "OMR_TEMPLATE_DIR" in os.environ:
        storage["templateDir"] = os.environ["OMR_TEMPLATE_DIR"]
