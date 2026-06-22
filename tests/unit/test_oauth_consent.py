"""Unit tests for the OAuth consent page renderer in `app.oauth_consent`.

These exercise `render_oauth_consent_page`/`_escape_js_string` directly with
no HTTP layer involved — see `tests/feature/test_oauth_consent.py` for the
route-reachability layer.
"""

from app.oauth_consent import _escape_js_string, render_oauth_consent_page


def test_render_oauth_consent_page_includes_pinned_exact_version_supabase_js_script_tag():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    assert (
        '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.108.2/dist/umd/supabase.js"></script>'
        in html_output
    )
    assert "@latest" not in html_output


def test_pinned_supabase_js_cdn_url_is_an_exact_version_not_a_range():
    import re

    from app.oauth_consent import _SUPABASE_JS_CDN_URL

    match = re.search(r"@supabase/supabase-js@([^/]+)/", _SUPABASE_JS_CDN_URL)
    assert match is not None
    version = match.group(1)

    assert version[0].isdigit()
    assert not version.startswith("^")
    assert not version.startswith("~")
    assert version != "latest"


def test_render_oauth_consent_page_injects_supabase_url_and_anon_key_as_js_constants():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key-123")

    assert 'const SUPABASE_URL = "https://example.supabase.co";' in html_output
    assert 'const SUPABASE_ANON_KEY = "anon-key-123";' in html_output


def test_render_oauth_consent_page_returns_200_compatible_full_html_document():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    assert html_output.startswith("<!DOCTYPE html>")
    assert "<title>Connect your account</title>" in html_output


def test_render_oauth_consent_page_embedded_js_reads_authorization_id_from_query_string():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    assert "window.location.search" in html_output
    assert 'params.get("authorization_id")' in html_output


def test_render_oauth_consent_page_embedded_js_renders_failure_state_when_authorization_id_missing():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    script_start = html_output.index("function lifecoachInit")
    script_body = html_output[script_start:]

    assert "if (!authorizationId)" in script_body
    assert "lifecoachRenderFailureState(" in script_body
    failure_branch = script_body.split("if (!authorizationId)")[1].split("return;")[0]
    assert "lifecoachRenderFailureState" in failure_branch
    assert "invalid or has expired" in failure_branch


def test_render_oauth_consent_page_does_not_initialize_supabase_client_on_missing_authorization_id_path():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    script_start = html_output.index("function lifecoachInit")
    script_body = html_output[script_start:]
    missing_id_branch = script_body.split("if (!authorizationId)")[1].split("return;")[0]

    assert "createClient" not in missing_id_branch


def test_render_oauth_consent_page_failure_message_is_clear_and_non_technical():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    assert "This link is invalid or has expired. Please try connecting again from the app." in html_output
    assert "Traceback" not in html_output
    assert "Exception" not in html_output


def test_escape_js_string_escapes_backslashes():
    assert _escape_js_string("a\\b") == "a\\\\b"


def test_escape_js_string_escapes_double_quotes():
    assert _escape_js_string('a"b') == 'a\\"b'


def test_escape_js_string_escapes_closing_script_tag_sequence():
    hostile = "</script><script>alert(1)</script>"

    escaped = _escape_js_string(hostile)

    assert "</script>" not in escaped
    assert "<\\/script>" in escaped


def test_escape_js_string_neutralizes_combined_quote_and_script_breakout_payload():
    hostile = '"; </script><script>alert(document.cookie)</script>//'

    escaped = _escape_js_string(hostile)

    assert "</script>" not in escaped
    assert escaped.count('\\"') >= 1


def test_render_oauth_consent_page_neutralizes_hostile_supabase_url_breakout_attempt():
    hostile_url = '"; }; alert(1); var x = {"a":"</script><script>alert(2)</script>'

    html_output = render_oauth_consent_page(hostile_url, "anon-key")

    assert "</script><script>alert(2)" not in html_output
    assert "<\\/script>" in html_output


def test_render_oauth_consent_page_neutralizes_hostile_anon_key_with_backslash_and_quote():
    hostile_key = 'abc\\"; alert(1); //'

    html_output = render_oauth_consent_page("https://example.supabase.co", hostile_key)

    expected_literal = _escape_js_string(hostile_key)
    expected_line = f'const SUPABASE_ANON_KEY = "{expected_literal}";'

    assert expected_line in html_output
    # The unescaped payload must never appear verbatim: a real double-quote
    # immediately followed by `; alert(1)` would terminate the JS string
    # literal and let `alert(1)` execute as a statement.
    assert 'abc"; alert(1); //' not in html_output
