import importlib
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.config import get_settings

ENV_VARS = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
}

MIGRATIONS_ENV_PATH = Path(__file__).resolve().parents[2] / "migrations" / "env.py"


def _load_migrations_env(mock_context):
    spec = importlib.util.spec_from_file_location("migrations_env_under_test", MIGRATIONS_ENV_PATH)
    module = importlib.util.module_from_spec(spec)

    fake_alembic_context_module = ModuleType("alembic.context")
    fake_alembic_context_module.__dict__.update(vars(mock_context))

    original_alembic_context = sys.modules.get("alembic.context")
    sys.modules["alembic.context"] = mock_context
    try:
        spec.loader.exec_module(module)
    finally:
        if original_alembic_context is not None:
            sys.modules["alembic.context"] = original_alembic_context
        else:
            sys.modules.pop("alembic.context", None)

    return module


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    for key, value in ENV_VARS.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_env_py_sources_sqlalchemy_url_from_app_settings(monkeypatch):
    mock_config = MagicMock()
    mock_config.config_file_name = None

    mock_context = MagicMock()
    mock_context.config = mock_config
    mock_context.is_offline_mode.return_value = True

    monkeypatch.setattr("alembic.context", mock_context)

    _load_migrations_env(mock_context)

    mock_config.set_main_option.assert_called_once_with(
        "sqlalchemy.url", ENV_VARS["DATABASE_URL"]
    )


def test_env_py_uses_database_url_from_settings_not_a_hardcoded_value(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://other:pw@otherhost:5432/otherdb")
    get_settings.cache_clear()

    mock_config = MagicMock()
    mock_config.config_file_name = None

    mock_context = MagicMock()
    mock_context.config = mock_config
    mock_context.is_offline_mode.return_value = True

    monkeypatch.setattr("alembic.context", mock_context)

    _load_migrations_env(mock_context)

    mock_config.set_main_option.assert_called_once_with(
        "sqlalchemy.url", "postgresql://other:pw@otherhost:5432/otherdb"
    )
