import json
from pathlib import Path

import pytest

from src.services.service_config import DEFAULT_SERVER_WORKERS, load_service_config


def test_load_service_config_resolves_env_placeholders(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_SECRET_ID", "sid")
    monkeypatch.setenv("COS_SECRET_KEY", "skey")
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text(json.dumps({
        "server": {"port": 8081, "workers": 2},
        "storage": {"serviceDataDir": "service_data", "templateDir": "inputs", "archivePrefix": "omr-archive"},
        "database": {"url": "sqlite:///service_data/omr_service.db"},
        "cos": {"enabled": True, "region": "ap-guangzhou", "bucket": "bucket", "secretId": "${COS_SECRET_ID}", "secretKey": "${COS_SECRET_KEY}"},
        "callback": {"url": "${OMR_CALLBACK_TARGET}", "maxAttempts": 3, "timeoutSeconds": 10}
    }), encoding="utf-8")
    monkeypatch.setenv("OMR_CALLBACK_TARGET", "https://callback.example.test/omr")

    config = load_service_config(config_path)

    assert config.server.port == 8081
    assert config.server.workers == 2
    assert config.cos.secret_id == "sid"
    assert config.cos.secret_key == "skey"
    assert config.callback.url == "https://callback.example.test/omr"


def test_load_service_config_reads_env_file_for_cos_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COS_SECRET_ID", raising=False)
    monkeypatch.delenv("COS_SECRET_KEY", raising=False)
    (tmp_path / ".env").write_text(
        'COS_SECRET_ID="sid-from-env-file"\nCOS_SECRET_KEY=skey-from-env-file\n',
        encoding="utf-8",
    )
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text(json.dumps({
        "cos": {
            "enabled": True,
            "region": "ap-guangzhou",
            "bucket": "bucket",
            "secretId": "${COS_SECRET_ID}",
            "secretKey": "${COS_SECRET_KEY}",
        }
    }), encoding="utf-8")

    config = load_service_config(config_path)

    assert config.cos.secret_id == "sid-from-env-file"
    assert config.cos.secret_key == "skey-from-env-file"


def test_load_service_config_allows_environment_port_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OMR_SERVICE_PORT", "9090")
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text("{}", encoding="utf-8")

    config = load_service_config(config_path)

    assert config.server.port == 9090
    assert config.storage.template_dir == Path("inputs")


def test_server_workers_default_to_cpu_count_when_unset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMR_SERVICE_WORKERS", raising=False)
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text("{}", encoding="utf-8")

    config = load_service_config(config_path)

    assert config.server.workers == DEFAULT_SERVER_WORKERS


def test_server_workers_can_be_configured_from_json_and_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMR_SERVICE_WORKERS", raising=False)
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"server": {"workers": 3}}', encoding="utf-8")

    assert load_service_config(config_path).server.workers == 3

    monkeypatch.setenv("OMR_SERVICE_WORKERS", "5")
    assert load_service_config(config_path).server.workers == 5

    monkeypatch.setenv("OMR_SERVICE_WORKERS", "auto")
    assert load_service_config(config_path).server.workers == DEFAULT_SERVER_WORKERS


def test_server_workers_must_be_positive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMR_SERVICE_WORKERS", raising=False)
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"server": {"workers": 0}}', encoding="utf-8")

    with pytest.raises(ValueError, match="server.workers"):
        load_service_config(config_path)


def test_load_service_config_allows_environment_callback_url_override(tmp_path, monkeypatch):
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"callback": {"url": "https://json.example.test/callback"}}', encoding="utf-8")
    monkeypatch.setenv("OMR_CALLBACK_URL", "https://env.example.test/callback")

    config = load_service_config(config_path)

    assert config.callback.url == "https://env.example.test/callback"


def test_load_service_config_rejects_malformed_callback_url(tmp_path, monkeypatch):
    config_path = tmp_path / "robyn-service.json"
    config_path.write_text('{"callback": {"url": "https:/localhost:8080/callback"}}', encoding="utf-8")

    with pytest.raises(ValueError, match="callback.url must be a valid"):
        load_service_config(config_path)


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
