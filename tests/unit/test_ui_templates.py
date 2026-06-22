"""Unit tests for `app.ui_templates` under the MCP Apps (SEP-1865)
architecture: `render_home_view`/`render_goal_detail_view` return a static
HTML template containing client-side rendering JS — they take no data
argument, so server-side HTML output can no longer be asserted against
data inputs. Rendering itself now happens in the browser; these tests can
only assert against the JS *source* (function presence, structure, and the
escaping logic itself), not its executed output.

`home_view_data_to_dict`/`goal_detail_data_to_dict` remain real Python
logic (camelCase mapping or the data the client renders) and are tested
thoroughly here, the same way the old suite tested server-side rendering.

See `tests/unit/test_mcp_server.py` for the tool-logic layer that builds
the dataclasses these helpers convert, and
`tests/feature/test_mcp_get_home_view.py` etc. for the wire-protocol layer.
"""

import re

from app.ui_templates import (
    GoalDetailUpdate,
    GoalDetailViewData,
    HomeGoalCard,
    HomeViewData,
    goal_detail_data_to_dict,
    home_view_data_to_dict,
    render_goal_detail_view,
    render_home_view,
)


def _card(**overrides):
    defaults = dict(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        progress_percent=None,
        last_updated_at=None,
    )
    defaults.update(overrides)
    return HomeGoalCard(**defaults)


# ---------------------------------------------------------------------------
# render_home_view / render_goal_detail_view: static template + JS bridge
# ---------------------------------------------------------------------------


def test_render_home_view_takes_no_arguments():
    import inspect

    signature = inspect.signature(render_home_view)

    assert len(signature.parameters) == 0


def test_render_goal_detail_view_takes_no_arguments():
    import inspect

    signature = inspect.signature(render_goal_detail_view)

    assert len(signature.parameters) == 0


def test_render_home_view_returns_full_html_document():
    html_output = render_home_view()

    assert html_output.startswith("<!DOCTYPE html>")
    assert "<html" in html_output
    assert '<div class="page" id="root">' in html_output


def test_render_goal_detail_view_returns_full_html_document():
    html_output = render_goal_detail_view()

    assert html_output.startswith("<!DOCTYPE html>")
    assert "<html" in html_output
    assert '<div class="page" id="root">' in html_output


def test_render_home_view_is_deterministic_static_template():
    assert render_home_view() == render_home_view()


def test_render_goal_detail_view_is_deterministic_static_template():
    assert render_goal_detail_view() == render_goal_detail_view()


def test_render_home_view_includes_bridge_js_initialize_handshake():
    html_output = render_home_view()

    assert 'method: "ui/initialize"' in html_output
    assert "window.parent.postMessage" in html_output
    assert "window.callTool" in html_output
    assert "window.sendMessage" in html_output


def test_render_goal_detail_view_includes_bridge_js_initialize_handshake():
    html_output = render_goal_detail_view()

    assert 'method: "ui/initialize"' in html_output
    assert "window.parent.postMessage" in html_output
    assert "window.callTool" in html_output
    assert "window.sendMessage" in html_output


def test_render_home_view_includes_render_functions():
    html_output = render_home_view()

    assert "function renderHomeView(" in html_output
    assert "function renderGoalDetailView(" in html_output
    assert "function escapeHtml(" in html_output
    assert "function goalCard(" in html_output


def test_render_goal_detail_view_includes_render_functions():
    html_output = render_goal_detail_view()

    assert "function renderHomeView(" in html_output
    assert "function renderGoalDetailView(" in html_output
    assert "function escapeHtml(" in html_output


def test_render_home_view_wires_tool_result_callback_to_render_home_view():
    html_output = render_home_view()

    assert "window.onToolResult" in html_output
    callback_section = html_output.split("window.onToolResult")[1]
    assert "renderHomeView(data)" in callback_section


def test_render_goal_detail_view_wires_tool_result_callback_to_render_goal_detail_view():
    html_output = render_goal_detail_view()

    assert "window.onToolResult" in html_output
    callback_section = html_output.split("window.onToolResult")[1]
    assert "renderGoalDetailView(data)" in callback_section


def test_render_home_view_has_no_tab_bar_or_streak_markup():
    html_output = render_home_view().lower()

    assert "tab-bar" not in html_output
    assert "reflect" not in html_output
    assert "journey" not in html_output
    assert "current streak" not in html_output


def test_render_goal_detail_view_has_no_tab_bar_or_streak_markup():
    html_output = render_goal_detail_view().lower()

    assert "tab-bar" not in html_output
    assert "reflect" not in html_output
    assert "journey" not in html_output
    assert "current streak" not in html_output


def test_render_home_view_never_mentions_transcript():
    assert "transcript" not in render_home_view().lower()


def test_render_goal_detail_view_never_mentions_transcript():
    assert "transcript" not in render_goal_detail_view().lower()


# ---------------------------------------------------------------------------
# escapeHtml JS implementation: verify the five-character escaping discipline
# migrated correctly from Python's html.escape into the client-side JS
# ---------------------------------------------------------------------------


def _extract_escape_html_body(html_output: str) -> str:
    start = html_output.index("function escapeHtml(")
    # Body runs from the first '{' after the signature to the matching '}'
    # — escapeHtml is a short, single-level function, so a depth-aware scan
    # from the opening brace is sufficient and avoids relying on exact
    # surrounding formatting.
    open_brace = html_output.index("{", start)
    depth = 0
    i = open_brace
    while True:
        if html_output[i] == "{":
            depth += 1
        elif html_output[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return html_output[open_brace : i + 1]


def test_escape_html_js_escapes_ampersand_first():
    body = _extract_escape_html_body(render_home_view())

    amp_idx = body.index("/&/g")
    lt_idx = body.index("/</g")
    assert amp_idx < lt_idx, "escaping & after < or > would double-escape entities"


def test_escape_html_js_covers_all_five_html_special_characters():
    body = _extract_escape_html_body(render_home_view())

    assert "/&/g" in body
    assert "/</g" in body
    assert "/>/g" in body
    assert '/"/g' in body
    assert "/'/g" in body


def test_escape_html_js_replacement_entities_match_python_html_escape():
    import html as html_module

    body = _extract_escape_html_body(render_home_view())

    assert "&amp;amp;" not in body  # sanity: not double-escaping itself
    assert "&amp;" in body
    assert "&lt;" in body
    assert "&gt;" in body
    assert "&quot;" in body
    assert "&#x27;" in body

    # Cross-check against Python's html.escape, the prior server-side
    # implementation, to confirm the replacement set is equivalent.
    payload = """<script>alert('x & "y"')</script>"""
    assert html_module.escape(payload) == (
        "&lt;script&gt;alert(&#x27;x &amp; &quot;y&quot;&#x27;)&lt;/script&gt;"
    )


def test_escape_html_js_handles_non_string_input_without_throwing():
    body = _extract_escape_html_body(render_home_view())

    assert "typeof s !== 'string'" in body


# ---------------------------------------------------------------------------
# onclick interpolation discipline: only the server-generated UUID `id` may
# be interpolated into a JS-execution (onclick) context. This is the same
# property the prior server-rendered template enforced via
# `lifecoachContinueGoal('{GOAL_ID}')`-style calls.
# ---------------------------------------------------------------------------


def _onclick_values(html_output: str) -> list[str]:
    return re.findall(r'onclick="([^"]*)"', html_output)


def test_goal_card_onclick_interpolates_only_safe_id_via_calltool():
    html_output = render_home_view()
    goal_card_fn = html_output[html_output.index("function goalCard(") :]
    goal_card_fn = goal_card_fn[: goal_card_fn.index("\nfunction ", 1)]

    onclick_segment = goal_card_fn[
        goal_card_fn.index("onclick=") : goal_card_fn.index(")", goal_card_fn.index("onclick="))
    ]

    assert "window.callTool" in onclick_segment
    assert "get_goal_detail_view" in onclick_segment
    assert "safeId" in onclick_segment
    assert "safeTitle" not in onclick_segment


def test_render_goal_detail_view_delete_actions_interpolate_only_uuid_into_onclick():
    html_output = render_goal_detail_view()
    detail_fn_start = html_output.index("function renderGoalDetailView(")
    detail_fn = html_output[detail_fn_start:]
    detail_fn = detail_fn[: detail_fn.index("\nfunction renderGoalDetailError")]

    assert "showDeleteConfirm(\\'' + safeId + '\\')" in detail_fn
    assert "confirmDelete(\\'' + safeId + '\\')" in detail_fn
    assert "cancelDeleteConfirm(\\'' + safeId + '\\')" in detail_fn


def test_render_goal_detail_view_continue_button_interpolates_only_uuid_into_onclick():
    """The continue-conversation button's onclick handler must only ever
    interpolate the trusted server-generated UUID (`safeId`) into the
    onclick JS-string context, never the free-text, user-controlled goal
    title — same invariant already enforced for the delete actions.

    HTML-escaping a title and then concatenating it into a single-quoted
    JS string literal inside an `onclick` attribute is NOT safe: the
    browser HTML-decodes attribute values before the JS engine parses the
    onclick handler's source, so an escaped quote (`&#x27;`) decodes back
    to a raw `'` at the point JS parses it, allowing a hostile title to
    break out of the string and execute arbitrary script. The fix is to
    pass only the UUID into onclick (`continueGoal('<uuid>')`) and have
    that JS function read the already-escaped title back from the DOM via
    `textContent` at click time, exactly like the old server-rendered
    template did.
    """
    html_output = render_goal_detail_view()
    detail_fn_start = html_output.index("function renderGoalDetailView(")
    detail_fn = html_output[detail_fn_start:]
    detail_fn = detail_fn[: detail_fn.index("\nfunction renderGoalDetailError")]

    continue_button_line = next(
        line for line in detail_fn.splitlines() if "continue-entry" in line
    )

    assert "safeTitle" not in continue_button_line
    assert "continueGoal(\\'' + safeId + '\\')" in continue_button_line

    assert "function continueGoal(goalId)" in html_output
    continue_fn_start = html_output.index("function continueGoal(")
    continue_fn = html_output[continue_fn_start : continue_fn_start + 300]
    assert "textContent" in continue_fn
    assert "window.sendMessage(" in continue_fn


# ---------------------------------------------------------------------------
# home_view_data_to_dict
# ---------------------------------------------------------------------------


def test_home_view_data_to_dict_maps_camel_case_fields():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[
            _card(
                id="11111111-1111-1111-1111-111111111111",
                title="Run a 5k",
                progress_percent=42,
                last_updated_at="2026-06-15T10:00:00+00:00",
            )
        ],
    )

    result = home_view_data_to_dict(data)

    assert result == {
        "greetingName": "Sam",
        "goals": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "title": "Run a 5k",
                "progressPercent": 42,
                "lastUpdatedAt": "2026-06-15T10:00:00+00:00",
            }
        ],
        "error": None,
    }


def test_home_view_data_to_dict_preserves_none_progress_percent_not_coerced_to_zero():
    data = HomeViewData(greeting_name="Sam", goals=[_card(progress_percent=None)])

    result = home_view_data_to_dict(data)

    assert result["goals"][0]["progressPercent"] is None


def test_home_view_data_to_dict_preserves_zero_progress_percent_distinct_from_none():
    data = HomeViewData(greeting_name="Sam", goals=[_card(progress_percent=0)])

    result = home_view_data_to_dict(data)

    assert result["goals"][0]["progressPercent"] == 0


def test_home_view_data_to_dict_maps_multiple_goals_in_order():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[
            _card(id="11111111-1111-1111-1111-111111111111", title="Goal A"),
            _card(id="22222222-2222-2222-2222-222222222222", title="Goal B"),
        ],
    )

    result = home_view_data_to_dict(data)

    assert [g["title"] for g in result["goals"]] == ["Goal A", "Goal B"]


def test_home_view_data_to_dict_empty_goals_list():
    data = HomeViewData(greeting_name="Sam", goals=[])

    result = home_view_data_to_dict(data)

    assert result["goals"] == []
    assert result["error"] is None


def test_home_view_data_to_dict_error_short_circuits_before_goals_or_greeting():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[_card(title="Should not leak")],
        error="We couldn't load your home screen right now.",
    )

    result = home_view_data_to_dict(data)

    assert result == {
        "greetingName": None,
        "goals": [],
        "error": "We couldn't load your home screen right now.",
    }
    assert "Should not leak" not in str(result)


def test_home_view_data_to_dict_no_error_sets_error_key_to_none_explicitly():
    data = HomeViewData(greeting_name="Sam", goals=[])

    result = home_view_data_to_dict(data)

    assert "error" in result
    assert result["error"] is None


def test_home_view_data_to_dict_never_includes_transcript_key():
    data = HomeViewData(greeting_name="Sam", goals=[_card()])

    result = home_view_data_to_dict(data)

    assert "transcript" not in result
    for goal in result["goals"]:
        assert "transcript" not in goal


# ---------------------------------------------------------------------------
# goal_detail_data_to_dict
# ---------------------------------------------------------------------------


def test_goal_detail_data_to_dict_maps_camel_case_fields():
    update = GoalDetailUpdate(content="Ran 3 miles today", created_at="2026-06-15T10:00:00+00:00")
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[update],
    )

    result = goal_detail_data_to_dict(data)

    assert result == {
        "id": "33333333-3333-3333-3333-333333333333",
        "title": "Run a 5k",
        "description": "Train three times a week",
        "progressPercent": 42,
        "recentUpdates": [
            {"content": "Ran 3 miles today", "createdAt": "2026-06-15T10:00:00+00:00"}
        ],
        "error": None,
    }


def test_goal_detail_data_to_dict_preserves_none_progress_percent_not_coerced_to_zero():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=None,
        recent_updates=[],
    )

    result = goal_detail_data_to_dict(data)

    assert result["progressPercent"] is None


def test_goal_detail_data_to_dict_preserves_zero_progress_percent_distinct_from_none():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=0,
        recent_updates=[],
    )

    result = goal_detail_data_to_dict(data)

    assert result["progressPercent"] == 0


def test_goal_detail_data_to_dict_maps_multiple_recent_updates_in_order():
    updates = [
        GoalDetailUpdate(content="First", created_at="2026-06-14T10:00:00+00:00"),
        GoalDetailUpdate(content="Second", created_at="2026-06-15T10:00:00+00:00"),
    ]
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=42,
        recent_updates=updates,
    )

    result = goal_detail_data_to_dict(data)

    assert [u["content"] for u in result["recentUpdates"]] == ["First", "Second"]


def test_goal_detail_data_to_dict_empty_recent_updates_list():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=None,
        recent_updates=[],
    )

    result = goal_detail_data_to_dict(data)

    assert result["recentUpdates"] == []


def test_goal_detail_data_to_dict_error_short_circuits_before_any_other_data_leaks():
    update = GoalDetailUpdate(content="should not appear", created_at="2026-06-15T10:00:00+00:00")
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[update],
        error="This goal isn't available.",
    )

    result = goal_detail_data_to_dict(data)

    assert result == {"error": "This goal isn't available."}
    assert "id" not in result
    assert "title" not in result
    assert "description" not in result
    assert "progressPercent" not in result
    assert "recentUpdates" not in result


def test_goal_detail_data_to_dict_no_error_sets_error_key_to_none_explicitly():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=None,
        recent_updates=[],
    )

    result = goal_detail_data_to_dict(data)

    assert "error" in result
    assert result["error"] is None


def test_goal_detail_data_to_dict_never_includes_transcript_key():
    update = GoalDetailUpdate(content="Ran 3 miles today", created_at="2026-06-15T10:00:00+00:00")
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[update],
    )

    result = goal_detail_data_to_dict(data)

    assert "transcript" not in result
    for update_dict in result["recentUpdates"]:
        assert "transcript" not in update_dict
