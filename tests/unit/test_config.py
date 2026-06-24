import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


ENV_VARS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
}


def test_loads_settings_from_environment_variables(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.supabase_url == ENV_VARS["SUPABASE_URL"]
    assert settings.supabase_anon_key == ENV_VARS["SUPABASE_ANON_KEY"]
    assert settings.database_url == ENV_VARS["DATABASE_URL"]


def test_raises_when_required_environment_variables_are_missing(monkeypatch):
    for key in ENV_VARS:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()


def test_rate_limit_settings_default_when_not_set_in_environment(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("RATE_LIMIT_REQUESTS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_WINDOW_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.rate_limit_requests == 30
    assert settings.rate_limit_window_seconds == 60


def test_rate_limit_settings_are_overridable_via_environment_variables(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "10")

    settings = Settings(_env_file=None)

    assert settings.rate_limit_requests == 5
    assert settings.rate_limit_window_seconds == 10


def test_mcp_allowed_hosts_default_to_localhost_for_local_dev(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("MCP_ALLOWED_ORIGINS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.mcp_allowed_hosts_list == ["localhost:8001", "127.0.0.1:8001"]
    assert settings.mcp_allowed_origins_list == [
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ]


def test_mcp_allowed_hosts_overridable_via_environment_variable(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "lifecoach-api.onrender.com")
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://lifecoach-api.onrender.com")

    settings = Settings(_env_file=None)

    assert settings.mcp_allowed_hosts_list == ["lifecoach-api.onrender.com"]
    assert settings.mcp_allowed_origins_list == ["https://lifecoach-api.onrender.com"]


def test_mcp_allowed_hosts_list_splits_and_strips_comma_separated_values(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "host-a.com, host-b.com ,host-c.com")

    settings = Settings(_env_file=None)

    assert settings.mcp_allowed_hosts_list == ["host-a.com", "host-b.com", "host-c.com"]
