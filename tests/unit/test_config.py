import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


ENV_VARS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    "SUPABASE_JWT_SECRET": "jwt-secret",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
}


def test_loads_settings_from_environment_variables(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)

    assert settings.supabase_url == ENV_VARS["SUPABASE_URL"]
    assert settings.supabase_anon_key == ENV_VARS["SUPABASE_ANON_KEY"]
    assert settings.supabase_service_role_key == ENV_VARS["SUPABASE_SERVICE_ROLE_KEY"]
    assert settings.supabase_jwt_secret == ENV_VARS["SUPABASE_JWT_SECRET"]
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
