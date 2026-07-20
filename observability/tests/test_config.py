from __future__ import annotations

import pytest

from app.config import Settings

_REQUIRED_ENV = {
    "OBSERVABILITY_GRPC_PORT": "50056",
    "OBSERVABILITY_HTTP_PORT": "8086",
    "POSTGRES_DSN": "postgresql://user:pass@localhost/aecp",
    "OTEL_COLLECTOR_ENDPOINT": "otel-collector:4317",
    "ALLOWED_CALLERS": "coordinator",
}


def _set_env(monkeypatch, overrides=None):
    env = {**_REQUIRED_ENV, **(overrides or {})}
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_from_env_loads_all_required_settings(monkeypatch) -> None:
    _set_env(monkeypatch)
    settings = Settings.from_env()

    assert settings.grpc_port == 50056
    assert settings.http_port == 8086
    assert settings.postgres_dsn == "postgresql://user:pass@localhost/aecp"
    assert settings.otel_collector_endpoint == "otel-collector:4317"
    assert settings.allowed_callers == ("coordinator",)
    assert settings.mtls_cert_file == ""
    assert settings.mtls_key_file == ""
    assert settings.mtls_ca_file == ""


@pytest.mark.parametrize("missing_key", list(_REQUIRED_ENV))
def test_from_env_fails_closed_on_missing_required_value(monkeypatch, missing_key) -> None:
    overrides = {k: v for k, v in _REQUIRED_ENV.items() if k != missing_key}
    for key in _REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValueError):
        Settings.from_env()


def test_from_env_rejects_out_of_range_ports(monkeypatch) -> None:
    _set_env(monkeypatch, {"OBSERVABILITY_GRPC_PORT": "70000"})
    with pytest.raises(ValueError):
        Settings.from_env()


def test_from_env_rejects_empty_allowed_callers(monkeypatch) -> None:
    _set_env(monkeypatch, {"ALLOWED_CALLERS": "  , "})
    with pytest.raises(ValueError):
        Settings.from_env()


def test_from_env_defaults_mtls_files_to_empty_string(monkeypatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("MTLS_CERT_FILE", raising=False)
    monkeypatch.delenv("MTLS_KEY_FILE", raising=False)
    monkeypatch.delenv("MTLS_CA_FILE", raising=False)

    settings = Settings.from_env()
    assert settings.mtls_cert_file == ""
    assert settings.mtls_key_file == ""
    assert settings.mtls_ca_file == ""


def test_from_env_accepts_multiple_allowed_callers(monkeypatch) -> None:
    _set_env(monkeypatch, {"ALLOWED_CALLERS": "coordinator, gateway"})
    settings = Settings.from_env()
    assert settings.allowed_callers == ("coordinator", "gateway")
