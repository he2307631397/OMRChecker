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
