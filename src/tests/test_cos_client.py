import sys
from types import SimpleNamespace

import pytest

from src.services.service_config import CosConfig
from src.services.cos_client import LocalCosClient, TencentCosClient, build_cos_client


def test_local_cos_client_download_upload_binary_roundtrip_and_creates_parent_dirs(tmp_path):
    client = LocalCosClient(tmp_path / "cos-root")
    source = tmp_path / "source.bin"
    source.write_bytes(b"\x00omr\xffbytes")

    client.upload_file(source, "artifacts/run-1/output.bin", content_type="application/octet-stream")

    stored_path = tmp_path / "cos-root" / "artifacts" / "run-1" / "output.bin"
    assert stored_path.read_bytes() == b"\x00omr\xffbytes"

    destination = tmp_path / "downloads" / "nested" / "output.bin"
    client.download_file("artifacts/run-1/output.bin", destination)

    assert destination.read_bytes() == b"\x00omr\xffbytes"


def test_local_cos_client_missing_osskey_raises_file_not_found(tmp_path):
    client = LocalCosClient(tmp_path / "cos-root")

    with pytest.raises(FileNotFoundError):
        client.download_file("missing/object.pdf", tmp_path / "out.pdf")


def test_build_cos_client_returns_local_client_when_cos_disabled(tmp_path):
    config = CosConfig(enabled=False, local_root=tmp_path / "configured-cos")

    client = build_cos_client(config)

    assert isinstance(client, LocalCosClient)
    source = tmp_path / "input.dat"
    source.write_bytes(b"local")
    client.upload_file(source, "folder/input.dat")
    assert (tmp_path / "configured-cos" / "folder" / "input.dat").read_bytes() == b"local"


def test_tencent_cos_client_constructs_without_sdk_or_network_and_sdk_error_is_clear(monkeypatch, tmp_path):
    config = CosConfig(enabled=True, region="ap-guangzhou", bucket="bucket", secret_id="sid", secret_key="skey")
    client = TencentCosClient(config)

    monkeypatch.setitem(sys.modules, "qcloud_cos", None)

    source = tmp_path / "input.bin"
    source.write_bytes(b"data")
    with pytest.raises(RuntimeError, match="qcloud_cos SDK is required"):
        client.upload_file(source, "input.bin")


def test_tencent_cos_client_upload_does_not_pass_unsupported_headers(monkeypatch, tmp_path):
    calls = []

    class FakeCosS3Client:
        def __init__(self, config):
            self.config = config

        def upload_file(self, **kwargs):
            calls.append(kwargs)

    fake_sdk = SimpleNamespace(
        CosConfig=lambda **kwargs: kwargs,
        CosS3Client=FakeCosS3Client,
    )
    monkeypatch.setitem(sys.modules, "qcloud_cos", fake_sdk)
    source = tmp_path / "checked.png"
    source.write_bytes(b"png")
    client = TencentCosClient(CosConfig(enabled=True, region="ap-guangzhou", bucket="bucket", secret_id="sid", secret_key="skey"))

    client.upload_file(source, "checked/task/sheet/checked.png", content_type="image/png")

    assert calls == [
        {
            "Bucket": "bucket",
            "LocalFilePath": str(source),
            "Key": "checked/task/sheet/checked.png",
        }
    ]
