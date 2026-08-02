"""Object storage clients for Robyn service COS interactions."""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Protocol

from src.services.service_config import CosConfig


class ObjectStorageClient(Protocol):
    """Minimal object storage interface used by batch orchestration."""

    def download_file(self, osskey: str, destination_path: str | Path) -> None:
        """Download an object to a local file path."""

    def upload_file(self, local_path: str | Path, osskey: str, content_type: str | None = None) -> None:
        """Upload a local file to an object key."""


class LocalCosClient:
    """Filesystem-backed COS replacement for tests and local smoke runs."""

    def __init__(self, root: str | Path = Path("service_data/cos_mock")) -> None:
        self.root = Path(root)

    def download_file(self, osskey: str, destination_path: str | Path) -> None:
        source = self._object_path(osskey)
        if not source.is_file():
            raise FileNotFoundError(f"Local COS object not found: {osskey}")

        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def upload_file(self, local_path: str | Path, osskey: str, content_type: str | None = None) -> None:
        del content_type
        source = Path(local_path)
        destination = self._object_path(osskey)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def _object_path(self, osskey: str) -> Path:
        object_path = self.root / osskey.lstrip("/")
        resolved_root = self.root.resolve(strict=False)
        resolved_object = object_path.resolve(strict=False)
        if resolved_root != resolved_object and resolved_root not in resolved_object.parents:
            raise ValueError(f"OSS key escapes local COS root: {osskey}")
        return object_path


class TencentCosClient:
    """Tencent COS client that imports the SDK lazily when used."""

    def __init__(self, config: CosConfig) -> None:
        self.config = config
        self._client = None

    def download_file(self, osskey: str, destination_path: str | Path) -> None:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._get_client().download_file(
            Bucket=self.config.bucket,
            Key=osskey,
            DestFilePath=str(destination),
        )

    def upload_file(self, local_path: str | Path, osskey: str, content_type: str | None = None) -> None:
        kwargs: dict[str, object] = {
            "Bucket": self.config.bucket,
            "LocalFilePath": str(local_path),
            "Key": osskey,
        }
        if content_type is not None:
            kwargs["Headers"] = {"Content-Type": content_type}
        self._get_client().upload_file(**kwargs)

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            qcloud_cos = importlib.import_module("qcloud_cos")
        except ImportError as exc:
            raise RuntimeError(
                "qcloud_cos SDK is required for real Tencent COS operations. "
                "Install qcloud_cos or disable COS to use LocalCosClient."
            ) from exc

        config = qcloud_cos.CosConfig(
            Region=self.config.region,
            SecretId=self.config.secret_id,
            SecretKey=self.config.secret_key,
        )
        self._client = qcloud_cos.CosS3Client(config)
        return self._client


def build_cos_client(config: CosConfig) -> ObjectStorageClient:
    """Build the configured object storage client without performing network IO."""
    if config.enabled:
        return TencentCosClient(config)
    return LocalCosClient(config.local_root)
