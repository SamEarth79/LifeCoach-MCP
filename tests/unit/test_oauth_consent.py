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


def _extract_function_body(html_output: str, function_start_signature: str, next_function_signature: str) -> str:
    start = html_output.index(function_start_signature)
    end = html_output.index(next_function_signature, start)
    return html_output[start:end]


def test_render_login_or_consent_calls_get_authorization_details_when_session_active():
    """AC1: an active session fetches authorization details via the SDK."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_body = _extract_function_body(
        html_output, "async function renderLoginOrConsent", "function lifecoachInit"
    )
    session_branch = render_login_or_consent_body.split("if (!data.session)")[1].split(
        "return;"
    )[1]

    assert "client.auth.oauth.getAuthorizationDetails(" in session_branch
    assert "authorizationId" in session_branch.split("getAuthorizationDetails(")[1].split(")")[0]


def test_render_login_or_consent_routes_to_consent_screen_on_successful_details_fetch():
    """AC1: a successful fetch renders the consent screen with the fetched details."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_body = _extract_function_body(
        html_output, "async function renderLoginOrConsent", "function lifecoachInit"
    )

    assert "lifecoachRenderConsentScreen(client, authorizationId, details)" in render_login_or_consent_body


def test_render_login_or_consent_routes_to_failure_state_when_details_fetch_errors():
    """AC5: an error/missing-details response renders the SAME failure-state helper
    used for the missing-authorization_id case, not a new parallel implementation."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_body = _extract_function_body(
        html_output, "async function renderLoginOrConsent", "function lifecoachInit"
    )

    assert "if (error || !details)" in render_login_or_consent_body
    error_branch = render_login_or_consent_body.split("if (error || !details)")[1].split(
        "return;"
    )[0]
    assert "lifecoachRenderFailureState(" in error_branch
    assert "invalid or has expired" in error_branch


def test_render_login_or_consent_routes_to_failure_state_when_get_authorization_details_throws():
    """AC5: a thrown exception (network error, SDK throw) is also caught and routed
    to the same failure-state helper, not left to crash the page."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    render_login_or_consent_body = _extract_function_body(
        html_output, "async function renderLoginOrConsent", "function lifecoachInit"
    )

    assert "try {" in render_login_or_consent_body
    assert "catch (caughtError)" in render_login_or_consent_body
    catch_branch = render_login_or_consent_body.split("catch (caughtError)")[1]
    assert "lifecoachRenderFailureState(" in catch_branch
    assert "invalid or has expired" in catch_branch


def test_failure_state_helper_used_for_authorization_details_error_is_the_same_function_as_missing_id_case():
    """AC5: confirms reuse, not drift — the literal failure message used for both
    the getAuthorizationDetails error branch and its catch block is byte-identical
    to the one used for the missing-authorization_id case, and all three call
    sites invoke the single shared helper function rather than a new parallel one."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    failure_message = "This link is invalid or has expired. Please try connecting again from the app."
    # Three call sites share this exact literal message: the missing-authorization_id
    # branch (lifecoachInit), the getAuthorizationDetails error branch, and its
    # catch block (both in renderLoginOrConsent) -- all invoking the one shared helper.
    assert html_output.count(failure_message) == 3
    assert html_output.count("lifecoachRenderFailureState(\n") == 3
    assert html_output.count("function lifecoachRenderFailureState(") == 1


def test_render_consent_screen_renders_client_name_and_scopes():
    """AC1: client.name and each space-separated scope are rendered."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    assert "details.client.name" in consent_screen_body
    assert 'details.scope.split(" ")' in consent_screen_body
    assert "scope-item" in consent_screen_body
    assert "scope-list" in consent_screen_body


def test_render_consent_screen_escapes_client_name_with_html_escape_helper_not_js_string_escape():
    """AC2 (security-critical): client.name must go through lifecoachEscapeHtml,
    not _escape_js_string (wrong context for an innerHTML sink)."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    assert "lifecoachEscapeHtml(details.client.name)" in consent_screen_body


def test_render_consent_screen_escapes_every_scope_with_html_escape_helper():
    """AC2 (security-critical): each scope token is individually run through
    lifecoachEscapeHtml inside the .map() callback before being concatenated."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    map_callback = consent_screen_body.split(".map(function (scope)")[1].split("})")[0]
    assert "lifecoachEscapeHtml(scope)" in map_callback


def test_consent_screen_client_name_and_scopes_never_inserted_into_innerhtml_unescaped():
    """AC2: the only client-controlled values placed into the innerHTML-bound
    string are the already-escaped safeClientName/scopeItems variables -- the
    raw details.client.name / raw scope strings are never concatenated directly."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    innerhtml_assignment = consent_screen_body.split(".innerHTML =")[1].split(
        "document\n    .getElementById"
    )[0]

    assert "details.client.name" not in innerhtml_assignment
    assert "safeClientName" in innerhtml_assignment
    assert "scopeItems" in innerhtml_assignment


def test_lifecoach_escape_html_function_escapes_all_five_html_metacharacters():
    """Direct structural check that lifecoachEscapeHtml escapes &, <, >, ", ' --
    matching the behavior any HTML-escaping helper must provide."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    escape_html_body = _extract_function_body(
        html_output,
        "function lifecoachEscapeHtml",
        "function lifecoachRenderConsentScreen",
    )

    assert "/&/g" in escape_html_body
    assert "&amp;" in escape_html_body
    assert "/</g" in escape_html_body
    assert "&lt;" in escape_html_body
    assert "/>/g" in escape_html_body
    assert "&gt;" in escape_html_body
    assert '/"/g' in escape_html_body
    assert "&quot;" in escape_html_body
    assert "/'/g" in escape_html_body
    assert "&#39;" in escape_html_body


def _simulate_lifecoach_escape_html(value: str) -> str:
    """Pure-Python re-implementation mirroring the embedded JS lifecoachEscapeHtml
    function exactly, to assert behavior against constructed hostile payloads --
    the same approach used for _escape_js_string's hostile-payload tests above."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def test_lifecoach_escape_html_neutralizes_img_onerror_xss_payload_in_client_name_position():
    """AC2 (security-critical): a hostile client.name containing an <img onerror>
    XSS payload must have its angle brackets and quotes neutralized."""
    hostile_client_name = '<img src=x onerror=alert(1)>'

    escaped = _simulate_lifecoach_escape_html(hostile_client_name)

    assert "<img" not in escaped
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&lt;img src=x onerror=alert(1)&gt;" == escaped


def test_lifecoach_escape_html_neutralizes_attribute_breakout_payload_in_scope_position():
    """AC2 (security-critical): a hostile scope value containing a double-quote
    that could break out of an HTML attribute context must be escaped."""
    hostile_scope = 'read"><script>alert(document.cookie)</script>'

    escaped = _simulate_lifecoach_escape_html(hostile_scope)

    assert '"' not in escaped
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&quot;" in escaped
    assert "&lt;script&gt;" in escaped


def test_lifecoach_escape_html_neutralizes_single_quote_breakout_payload():
    """AC2: a hostile value using single quotes to break out of an attribute
    context is also neutralized, distinct from the double-quote case."""
    hostile_value = "x' onmouseover='alert(1)"

    escaped = _simulate_lifecoach_escape_html(hostile_value)

    assert "'" not in escaped
    assert "&#39;" in escaped


def test_lifecoach_escape_html_is_distinct_from_escape_js_string():
    """Confirms lifecoachEscapeHtml (HTML-entity escaping) and _escape_js_string
    (JS-string-literal escaping) are two different functions with different
    escaping rules -- using the wrong one for an innerHTML sink would be unsafe."""
    hostile_value = '<script>alert(1)</script>'

    html_escaped = _simulate_lifecoach_escape_html(hostile_value)
    js_escaped = _escape_js_string(hostile_value)

    assert html_escaped != js_escaped
    assert "&lt;script&gt;" in html_escaped
    assert "<\\/script>" in js_escaped
    assert "&lt;" not in js_escaped


def test_consent_screen_renders_approve_and_deny_buttons_wired_to_handler():
    """AC3/AC4: Approve and Deny buttons exist and are wired to
    lifecoachHandleConsentDecision with the correct decision string."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    assert 'id="oauth-consent-approve"' in consent_screen_body
    assert 'id="oauth-consent-deny"' in consent_screen_body
    assert "Approve" in consent_screen_body
    assert "Deny" in consent_screen_body

    approve_listener = consent_screen_body.split('getElementById("oauth-consent-approve")')[1].split(
        "});"
    )[0]
    assert 'lifecoachHandleConsentDecision(client, authorizationId, "approve")' in approve_listener

    deny_listener = consent_screen_body.split('getElementById("oauth-consent-deny")')[1].split(
        "});"
    )[0]
    assert 'lifecoachHandleConsentDecision(client, authorizationId, "deny")' in deny_listener


def test_handle_consent_decision_calls_approve_authorization_on_approve():
    """AC3: clicking Approve calls approveAuthorization(authorizationId)."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    approve_branch = handler_body.split('decision === "approve"')[1].split(":")[0]
    assert "client.auth.oauth.approveAuthorization(authorizationId)" in approve_branch


def test_handle_consent_decision_calls_deny_authorization_on_deny():
    """AC4: clicking Deny calls denyAuthorization(authorizationId)."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    deny_branch = handler_body.split('decision === "approve"')[1].split(":")[1].split(";")[0]
    assert "client.auth.oauth.denyAuthorization(authorizationId)" in deny_branch


def test_handle_consent_decision_navigates_to_redirect_url_on_success():
    """AC3/AC4: on success, the browser navigates via window.location.href to
    the returned redirect_url, for both approve and deny (shared code path)."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    assert "window.location.href = data.redirect_url;" in handler_body


def test_handle_consent_decision_shows_retryable_error_on_missing_redirect_url():
    """Edge case: error or missing data/redirect_url shows an error message
    without navigating, and does not remove or disable the buttons."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    assert "if (error || !data || !data.redirect_url)" in handler_body
    error_branch = handler_body.split("if (error || !data || !data.redirect_url)")[1].split(
        "return;"
    )[0]

    assert "errorEl.textContent" in error_branch
    assert "errorEl.hidden = false;" in error_branch
    assert "window.location" not in error_branch
    assert ".remove(" not in error_branch
    assert ".disabled" not in error_branch
    assert ".innerHTML" not in error_branch


def test_handle_consent_decision_shows_retryable_error_when_sdk_call_throws():
    """Edge case: a thrown exception (e.g. network failure) is caught and shows
    the same retryable error message, not an unhandled rejection."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    assert "try {" in handler_body
    assert "catch (caughtError)" in handler_body
    catch_branch = handler_body.split("catch (caughtError)")[1]
    assert "errorEl.textContent" in catch_branch
    assert "errorEl.hidden = false;" in catch_branch
    assert "window.location" not in catch_branch


def test_handle_consent_decision_clears_previous_error_state_at_start_of_each_attempt():
    """Retry behavior: a fresh attempt hides any previously shown error before
    making the SDK call, so a retry after a transient failure isn't stuck
    displaying the old error message indefinitely."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    handler_body = _extract_function_body(
        html_output,
        "async function lifecoachHandleConsentDecision",
        "function lifecoachRenderLoginForm",
    )

    pre_try_section = handler_body.split("try {")[0]
    assert 'getElementById("oauth-consent-action-error")' in pre_try_section
    assert "errorEl.hidden = true;" in pre_try_section


def test_consent_action_error_element_starts_hidden_in_rendered_markup():
    """The error placeholder is hidden by default until an actual failure occurs."""
    html_output = render_oauth_consent_page("https://example.supabase.co", "anon-key")

    consent_screen_body = _extract_function_body(
        html_output,
        "function lifecoachRenderConsentScreen",
        "async function lifecoachHandleConsentDecision",
    )

    assert 'id="oauth-consent-action-error" hidden' in consent_screen_body
