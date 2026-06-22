"""Feature test for the `GET /oauth/consent` route.

Drives the real FastAPI route through `TestClient`, the same pattern as
`tests/feature/test_health.py` — this proves the route is actually wired up
in `app.main`, returns the page unauthenticated, and that the page's
embedded JS contains the missing-`authorization_id` failure-state logic
required by this story. The full client-side login/consent flow (later
stories) is not exercised here since it doesn't exist yet; see
`tests/unit/test_oauth_consent.py` for the renderer-level assertions on the
failure-state JS structure.
"""

from fastapi.testclient import TestClient

from app import main
from app.config import Settings


def _client(monkeypatch):
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon-key-abc",
        database_url="postgresql://user:pass@localhost:5432/db",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    return TestClient(main.app)


def test_get_oauth_consent_returns_200_with_html_content_type(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/oauth/consent")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_get_oauth_consent_includes_pinned_supabase_js_script_and_injected_config(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/oauth/consent")

    body = response.text
    assert "@supabase/supabase-js@2.108.2" in body
    assert "@latest" not in body
    assert 'const SUPABASE_URL = "https://example.supabase.co";' in body
    assert 'const SUPABASE_ANON_KEY = "anon-key-abc";' in body


def test_get_oauth_consent_is_reachable_with_no_authorization_header(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/oauth/consent")

    assert response.status_code == 200
    assert "WWW-Authenticate" not in response.headers


def test_get_oauth_consent_with_authorization_header_present_still_succeeds(monkeypatch):
    # The route must not depend on/require a bearer token either way; a
    # caller that happens to send one (e.g. a generic HTTP client reusing
    # headers) should not be rejected.
    client = _client(monkeypatch)

    response = client.get("/oauth/consent", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 200


def test_get_oauth_consent_route_has_no_auth_or_rate_limit_dependency():
    route = next(route for route in main.app.routes if getattr(route, "path", None) == "/oauth/consent")

    dependant = route.dependant
    dependency_call_names = {dep.call.__name__ for dep in dependant.dependencies}

    assert "get_current_user" not in dependency_call_names
    assert "enforce_rate_limit" not in dependency_call_names


def test_get_oauth_consent_embedded_js_renders_failure_state_for_missing_authorization_id(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/oauth/consent")

    body = response.text
    assert 'params.get("authorization_id")' in body
    assert "if (!authorizationId)" in body
    failure_branch = body.split("if (!authorizationId)")[1].split("return;")[0]
    assert "lifecoachRenderFailureState" in failure_branch
    assert "invalid or has expired" in failure_branch
    assert "createClient" not in failure_branch
