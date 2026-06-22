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


def test_render_oauth_consent_page_renders_login_form_when_no_active_session():
    """AC1: no active session -> login form, not a consent screen."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_start = html_output.index("async function renderLoginOrConsent")
    render_login_or_consent_end = html_output.index(
        "function lifecoachInit", render_login_or_consent_start
    )
    render_login_or_consent_body = html_output[render_login_or_consent_start:render_login_or_consent_end]

    assert "client.auth.getSession()" in render_login_or_consent_body
    assert "if (!data.session)" in render_login_or_consent_body
    no_session_branch = render_login_or_consent_body.split("if (!data.session)")[1].split("return;")[0]
    assert "lifecoachRenderLoginForm(client, authorizationId)" in no_session_branch


def test_login_form_html_contains_email_and_password_fields_only():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_form_start = html_output.index("function lifecoachRenderLoginForm")
    render_login_form_end = html_output.index(
        "async function lifecoachHandleLoginSubmit", render_login_form_start
    )
    render_login_form_body = html_output[render_login_form_start:render_login_form_end]

    assert 'id="oauth-login-email"' in render_login_form_body
    assert 'type="email"' in render_login_form_body
    assert 'id="oauth-login-password"' in render_login_form_body
    assert 'type="password"' in render_login_form_body
    assert 'id="oauth-login-error"' in render_login_form_body


def test_login_form_submit_handler_is_wired_to_lifecoach_handle_login_submit():
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_form_start = html_output.index("function lifecoachRenderLoginForm")
    render_login_form_end = html_output.index(
        "async function lifecoachHandleLoginSubmit", render_login_form_start
    )
    render_login_form_body = html_output[render_login_form_start:render_login_form_end]

    assert 'addEventListener("submit"' in render_login_form_body
    assert "event.preventDefault();" in render_login_form_body
    assert "lifecoachHandleLoginSubmit(client, authorizationId);" in render_login_form_body


def test_handle_login_submit_calls_sign_in_with_password_with_email_and_password_argument_shape():
    """AC2: signInWithPassword is called with an {email, password} object."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handle_submit_start = html_output.index("async function lifecoachHandleLoginSubmit")
    handle_submit_end = html_output.index(
        "async function renderLoginOrConsent", handle_submit_start
    )
    handle_submit_body = html_output[handle_submit_start:handle_submit_end]

    assert "client.auth.signInWithPassword({ email, password })" in handle_submit_body
    assert 'document.getElementById("oauth-login-email").value' in handle_submit_body
    assert 'document.getElementById("oauth-login-password").value' in handle_submit_body


def test_handle_login_submit_calls_render_login_or_consent_on_success():
    """AC2: success path re-runs the session check, transitioning onward."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handle_submit_start = html_output.index("async function lifecoachHandleLoginSubmit")
    handle_submit_end = html_output.index(
        "async function renderLoginOrConsent", handle_submit_start
    )
    handle_submit_body = html_output[handle_submit_start:handle_submit_end]

    assert "if (error)" in handle_submit_body
    success_branch = handle_submit_body.split("if (error)")[1].split("return;")[1]
    assert "renderLoginOrConsent(client, authorizationId);" in success_branch


def test_handle_login_submit_shows_single_generic_error_message_on_invalid_credentials():
    """AC3: exactly one generic error string, not field- or reason-specific."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handle_submit_start = html_output.index("async function lifecoachHandleLoginSubmit")
    handle_submit_end = html_output.index(
        "async function renderLoginOrConsent", handle_submit_start
    )
    handle_submit_body = html_output[handle_submit_start:handle_submit_end]
    error_branch = handle_submit_body.split("if (error)")[1].split("return;")[0]

    assert "Invalid email or password." in error_branch
    assert html_output.count("Invalid email or password.") == 1

    lowered = handle_submit_body.lower()
    assert "email not found" not in lowered
    assert "no such user" not in lowered
    assert "wrong password" not in lowered
    assert "user not found" not in lowered
    assert "does not exist" not in lowered


def test_handle_login_submit_error_path_only_sets_error_text_and_does_not_navigate_or_remove_form():
    """AC3: failure must not navigate away or tear down the form."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handle_submit_start = html_output.index("async function lifecoachHandleLoginSubmit")
    handle_submit_end = html_output.index(
        "async function renderLoginOrConsent", handle_submit_start
    )
    handle_submit_body = html_output[handle_submit_start:handle_submit_end]
    error_branch = handle_submit_body.split("if (error)")[1].split("return;")[0]

    assert "window.location" not in error_branch
    assert ".remove(" not in error_branch
    assert ".innerHTML" not in error_branch
    assert 'errorEl.textContent = "Invalid email or password.";' in error_branch
    assert "errorEl.hidden = false;" in error_branch


def test_handle_login_submit_never_logs_or_echoes_submitted_credentials():
    """Security: email/password values must never be logged or echoed anywhere."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handle_submit_start = html_output.index("async function lifecoachHandleLoginSubmit")
    handle_submit_end = html_output.index(
        "async function renderLoginOrConsent", handle_submit_start
    )
    handle_submit_body = html_output[handle_submit_start:handle_submit_end]

    assert "console.log" not in handle_submit_body
    assert "console.error" not in handle_submit_body
    assert "console.warn" not in handle_submit_body

    error_branch = handle_submit_body.split("if (error)")[1].split("return;")[0]
    # The only allowed mention of "email"/"password" in the error path is the
    # fixed, generic literal string itself - never the `email`/`password`
    # variables holding the user's actual submitted values.
    error_branch_without_generic_message = error_branch.replace(
        "Invalid email or password.", ""
    )
    assert "email" not in error_branch_without_generic_message
    assert "password" not in error_branch_without_generic_message
    assert 'errorEl.textContent = "Invalid email or password.";' in error_branch


def test_no_signup_or_account_creation_text_anywhere_in_rendered_page():
    """AC4: no signup link or account-creation path appears anywhere."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    lowered = html_output.lower()
    for forbidden_phrase in (
        "sign up",
        "signup",
        "create account",
        "create an account",
        "register",
    ):
        assert forbidden_phrase not in lowered


def test_render_login_or_consent_shows_loading_state_when_session_already_active():
    """Active session -> skip the login form, show the loading/consent stub."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_start = html_output.index("async function renderLoginOrConsent")
    render_login_or_consent_end = html_output.index(
        "function lifecoachInit", render_login_or_consent_start
    )
    render_login_or_consent_body = html_output[render_login_or_consent_start:render_login_or_consent_end]

    session_branch = render_login_or_consent_body.split("if (!data.session)")[1].split(
        "return;"
    )[1]
    assert "lifecoachRenderLoadingState();" in session_branch
    assert "lifecoachRenderLoginForm" not in session_branch
