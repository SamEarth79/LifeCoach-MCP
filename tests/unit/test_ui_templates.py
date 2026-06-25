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
    GoalDetailTodo,
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


def test_render_home_view_reports_size_changes_to_host():
    """Without this, the host has no way to know how tall the actual
    content is and falls back to a default-sized iframe, forcing the user
    to scroll. Per the MCP Apps spec (SEP-1865), the view must notify the
    host via ui/notifications/size-changed - both right after the
    ui/initialize handshake and on every subsequent content size change
    (e.g. via ResizeObserver), since re-renders (home -> goal detail,
    delete-confirm expanding) change the content height after init."""
    html_output = render_home_view()

    assert 'method: "ui/notifications/size-changed"' in html_output
    assert "reportSize()" in html_output
    assert "new ResizeObserver(reportSize)" in html_output
    assert "getBoundingClientRect()" in html_output

    init_branch = html_output.split('msg.id === "__init__"')[1].split("return;")[0]
    assert "reportSize();" in init_branch


def test_render_goal_detail_view_reports_size_changes_to_host():
    html_output = render_goal_detail_view()

    assert 'method: "ui/notifications/size-changed"' in html_output
    assert "new ResizeObserver(reportSize)" in html_output


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


def test_render_home_view_includes_goal_detail_specific_styles():
    """Real bug: clicking a goal card from the home view does a client-side
    el.innerHTML = renderGoalDetailView(d) swap *inside the home page's own
    document* (see goalCard's onclick) - it never loads the separate
    ui://goal-detail-view resource. So if goal-detail-only CSS classes
    (.detail-title, .continue-entry, .update-item, etc.) only exist in a
    style block the home page never includes, the swapped-in detail markup
    renders with zero matching CSS - exactly what was observed live: the
    progress ring (shared style) looked fine, everything detail-specific
    didn't. Both templates must carry the same single combined stylesheet
    so this works regardless of which path renders the detail markup."""
    home_html = render_home_view()

    for css_class in (
        ".detail-title",
        ".detail-description",
        ".section-label",
        ".update-item",
        ".update-content",
        ".no-updates",
        ".continue-entry",
        ".delete-entry",
        ".delete-confirm",
    ):
        assert css_class in home_html


def test_home_and_detail_views_share_the_exact_same_stylesheet():
    home_html = render_home_view()
    detail_html = render_goal_detail_view()

    home_style = home_html.split("<style>")[1].split("</style>")[0]
    detail_style = detail_html.split("<style>")[1].split("</style>")[0]

    assert home_style == detail_style


def test_render_views_load_no_external_resources():
    """Real bug: MCP Apps run inside a sandboxed iframe with a restrictive
    default CSP that blocks external resources (fonts, scripts, etc.)
    unless explicitly declared via connectDomains/resourceDomains in the
    resource's _meta.ui.csp - which we don't declare. A Google Fonts
    <link> added during a redesign was silently blocked, and the rest of
    the stylesheet rendered as if unstyled in real Claude Desktop testing.
    These templates must rely only on system fonts and inline styles -
    no external <link>/<script src> to a third-party domain."""
    for html_output in (render_home_view(), render_goal_detail_view()):
        assert "fonts.googleapis.com" not in html_output
        assert "<link " not in html_output


def test_render_goal_detail_view_clamps_update_content_to_a_couple_of_lines():
    html_output = render_goal_detail_view()

    assert "-webkit-line-clamp: 2" in html_output
    assert "-webkit-box-orient: vertical" in html_output


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
# formatDate JS implementation: "Jul 12" style, not raw ISO "2026-07-12"
# ---------------------------------------------------------------------------


def _extract_function_body(html_output: str, signature: str) -> str:
    start = html_output.index(signature)
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


def _simulate_format_date(iso_string: str | None) -> str:
    """Pure-Python mirror of the embedded JS formatDate function, same
    approach used for lifecoachEscapeHtml elsewhere in this codebase."""
    if not iso_string:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    date_part = iso_string.split("T")[0]
    parts = date_part.split("-")
    if len(parts) != 3:
        return date_part
    try:
        month = months[int(parts[1]) - 1]
        day = int(parts[2])
    except (ValueError, IndexError):
        return date_part
    return f"{month} {day}"


def test_format_date_renders_month_abbreviation_and_day_not_raw_iso():
    assert _simulate_format_date("2026-07-12T10:00:00+00:00") == "Jul 12"
    assert _simulate_format_date("2026-01-05") == "Jan 5"
    assert _simulate_format_date("2026-12-31T23:59:59+00:00") == "Dec 31"


def test_format_date_handles_missing_value():
    assert _simulate_format_date(None) == ""
    assert _simulate_format_date("") == ""


def test_render_home_view_format_date_function_present_and_used_by_updated_line():
    html_output = render_home_view()

    assert "function formatDate(" in html_output
    format_date_body = _extract_function_body(html_output, "function formatDate(")
    assert '"Jan", "Feb", "Mar"' in format_date_body

    updated_line_body = _extract_function_body(html_output, "function updatedLine(")
    assert "formatDate(lastUpdatedAt)" in updated_line_body
    assert 'split("T")[0]' not in updated_line_body


def test_render_goal_detail_view_uses_format_date_for_update_dates():
    html_output = render_goal_detail_view()

    detail_fn_start = html_output.index("function renderGoalDetailView(")
    detail_fn = html_output[detail_fn_start : detail_fn_start + 2000]

    assert "formatDate(u.createdAt)" in detail_fn


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
# Todo checklist rendering (LFC-STORY-007-004): renderGoalDetailView's
# embedded JS builds the checklist client-side from data.todos, so — same
# constraint as every other renderGoalDetailView assertion in this file —
# these tests assert against the JS *source*, not executed/rendered output.
# No browser is executed anywhere in this suite; this matches the precedent
# already established for goalCard's onclick and the delete/continue actions
# above, and for the whole MCP Apps migration (see this file's module
# docstring and knowledge/implementations/LFC-004-mcp-ui-home-goal-views/
# test-results.md, which explicitly determined Playwright/browser E2E does
# not apply to this repo's MCP-UI surface: the HTML/JS is rendered by an
# external MCP-UI host - Claude Desktop or similar - that this repo doesn't
# control and has no route/page of its own to drive with Playwright. This is
# the first *interactive checklist* element, but not the first interactive
# element overall - goalCard's onclick, the delete-confirm two-stage flow,
# and continueGoal/toggleTodo's sibling pattern were already source-tested
# this same way, so this section follows that established pattern rather
# than introducing a new one.
# ---------------------------------------------------------------------------


def _render_goal_detail_view_function(html_output: str) -> str:
    start = html_output.index("function renderGoalDetailView(")
    body = html_output[start:]
    return body[: body.index("\nfunction renderGoalDetailError")]


def test_render_goal_detail_view_includes_todo_item_and_toggle_functions():
    html_output = render_goal_detail_view()

    assert "function todoItem(t)" in html_output
    assert "function toggleTodo(todoId)" in html_output


def test_render_goal_detail_view_renders_checklist_section_when_todos_present():
    detail_fn = _render_goal_detail_view_function(render_goal_detail_view())

    assert "data.todos && data.todos.length > 0" in detail_fn
    assert "Checklist" in detail_fn
    assert '<div class="todo-list">' in detail_fn
    assert "todoItem(data.todos[t])" in detail_fn


def test_render_goal_detail_view_iterates_todos_in_given_order():
    """AC3: the checklist is built with a plain ascending for-loop over
    data.todos, never sorted or reversed client-side - so render order is
    exactly whatever order the server already provided (sort_order ASC,
    per get_goal_detail_view's query)."""
    detail_fn = _render_goal_detail_view_function(render_goal_detail_view())

    loop_section = detail_fn[detail_fn.index("data.todos && data.todos.length > 0") :]
    loop_section = loop_section[: loop_section.index("</div>';") + len("</div>';")]

    assert "for (var t = 0; t < data.todos.length; t++)" in loop_section
    assert "data.todos[t]" in loop_section


def test_render_goal_detail_view_omits_checklist_entirely_when_todos_empty():
    """AC7: a goal with zero todos must not render an empty/broken
    checklist section - the section-label and todo-list wrapper are gated
    behind the same `data.todos.length > 0` check, never rendered alone."""
    detail_fn = _render_goal_detail_view_function(render_goal_detail_view())

    checklist_branch = detail_fn[
        detail_fn.index("if (data.todos") : detail_fn.index("html += '<p class=\"section-label\">Recent updates")
    ]

    assert checklist_branch.count("if (") == 1
    assert '<div class="todo-list">' in checklist_branch


def test_todo_item_function_renders_checkbox_and_text_reflecting_done_state():
    """AC3: checklist item is a checkbox + text, struck-through when done."""
    html_output = render_goal_detail_view()
    todo_item_fn = html_output[html_output.index("function todoItem(t)") :]
    todo_item_fn = todo_item_fn[: todo_item_fn.index("\nfunction toggleTodo")]

    assert 'type="checkbox"' in todo_item_fn
    assert "class=\"todo-checkbox\"" in todo_item_fn
    assert "t.done ? ' checked' : ''" in todo_item_fn
    assert "todo-done" in todo_item_fn
    assert "t.done ? ' todo-done' : ''" in todo_item_fn
    assert "safeText" in todo_item_fn
    assert "escapeHtml(t.text)" in todo_item_fn


def test_todo_item_onclick_interpolates_only_safe_id_never_free_text():
    """Same onclick-interpolation-discipline property enforced for every
    other interactive element in this file (goalCard, delete actions,
    continueGoal): only the trusted server-generated todo id may be
    interpolated into the onchange JS-string context, never the todo's
    free-text, user-controlled `text` field."""
    html_output = render_goal_detail_view()
    todo_item_fn = html_output[html_output.index("function todoItem(t)") :]
    todo_item_fn = todo_item_fn[: todo_item_fn.index("\nfunction toggleTodo")]

    onchange_line = next(line for line in todo_item_fn.splitlines() if "onchange=" in line)

    assert "toggleTodo(\\'' + safeId + '\\')" in onchange_line
    assert "safeText" not in onchange_line


def test_toggle_todo_calls_calltool_with_todo_id_and_disables_checkbox_first():
    """AC4: clicking a todo's checkbox calls toggle_todo via window.callTool
    with that todo's id; the checkbox disables itself immediately (so a
    second click can't fire while the first call is still in flight)."""
    html_output = render_goal_detail_view()
    toggle_fn_start = html_output.index("function toggleTodo(todoId)")
    toggle_fn = html_output[toggle_fn_start:]
    toggle_fn = toggle_fn[: toggle_fn.index("\nfunction renderGoalDetailError")]

    disable_idx = toggle_fn.index("checkbox.disabled = true")
    calltool_idx = toggle_fn.index('window.callTool("toggle_todo"')
    assert disable_idx < calltool_idx, "checkbox must disable before the tool call fires"

    assert '{ todo_id: todoId }' in toggle_fn


def test_toggle_todo_reconciles_checked_state_and_strikethrough_from_response():
    """AC4: once the tool call resolves, the checkbox's checked state and
    the text's strikethrough class must reflect the new done value from the
    response, and the checkbox must re-enable regardless of the result."""
    html_output = render_goal_detail_view()
    toggle_fn_start = html_output.index("function toggleTodo(todoId)")
    toggle_fn = html_output[toggle_fn_start:]
    toggle_fn = toggle_fn[: toggle_fn.index("\nfunction renderGoalDetailError")]

    assert "checkbox.checked = d.done" in toggle_fn
    assert "checkbox.disabled = false" in toggle_fn
    assert 'classList.add("todo-done")' in toggle_fn
    assert 'classList.remove("todo-done")' in toggle_fn


def test_render_goal_detail_view_has_no_add_edit_reorder_delete_todo_controls():
    """AC5: no other todo control (add/edit/reorder/delete) appears
    anywhere in the rendered output/JS - those remain conversational/
    tool-only. Checks the full document, not just renderGoalDetailView's
    body, since a stray control could in principle live elsewhere (e.g. in
    a shared action-list)."""
    html_output = render_goal_detail_view().lower()

    for forbidden in (
        "add todo",
        "add a todo",
        "new todo",
        "edit todo",
        "delete todo",
        "reorder",
        "create_todo",
        "update_todo",
        "delete_todo",
        "reorder_todos",
    ):
        assert forbidden not in html_output


def test_render_goal_detail_view_todo_section_styles_present_in_shared_stylesheet():
    html_output = render_goal_detail_view()

    for css_class in (".todo-list", ".todo-item", ".todo-checkbox", ".todo-text", ".todo-done"):
        assert css_class in html_output


def test_render_goal_detail_view_size_reporting_unaffected_by_todo_section():
    """AC6: the iframe size-reporting mechanism (ui/notifications/
    size-changed via reportSize()/ResizeObserver, established in
    test_render_goal_detail_view_reports_size_changes_to_host above) is
    declared once in the shared bridge JS, entirely independent of
    renderGoalDetailView's body - adding the todo-checklist branch to
    renderGoalDetailView cannot have touched it. Re-asserted here,
    scoped to confirm reportSize's wiring still sits outside
    renderGoalDetailView's own function body."""
    html_output = render_goal_detail_view()
    detail_fn = _render_goal_detail_view_function(html_output)

    assert "reportSize" not in detail_fn
    assert "ResizeObserver" not in detail_fn
    assert 'method: "ui/notifications/size-changed"' in html_output
    assert "new ResizeObserver(reportSize)" in html_output


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
    todo = GoalDetailTodo(id="44444444-4444-4444-4444-444444444444", text="Buy running shoes", done=False, sort_order=0)
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[update],
        todos=[todo],
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
        "todos": [
            {
                "id": "44444444-4444-4444-4444-444444444444",
                "text": "Buy running shoes",
                "done": False,
                "sortOrder": 0,
            }
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
        todos=[],
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
        todos=[],
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
        todos=[],
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
        todos=[],
    )

    result = goal_detail_data_to_dict(data)

    assert result["recentUpdates"] == []


def test_goal_detail_data_to_dict_maps_multiple_todos_in_sort_order():
    todos = [
        GoalDetailTodo(id="44444444-4444-4444-4444-444444444444", text="First", done=False, sort_order=0),
        GoalDetailTodo(id="55555555-5555-5555-5555-555555555555", text="Second", done=True, sort_order=1),
    ]
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=42,
        recent_updates=[],
        todos=todos,
    )

    result = goal_detail_data_to_dict(data)

    assert [t["text"] for t in result["todos"]] == ["First", "Second"]
    assert [t["done"] for t in result["todos"]] == [False, True]
    assert [t["sortOrder"] for t in result["todos"]] == [0, 1]


def test_goal_detail_data_to_dict_empty_todos_list():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=None,
        recent_updates=[],
        todos=[],
    )

    result = goal_detail_data_to_dict(data)

    assert result["todos"] == []


def test_goal_detail_data_to_dict_error_short_circuits_before_any_other_data_leaks():
    update = GoalDetailUpdate(content="should not appear", created_at="2026-06-15T10:00:00+00:00")
    todo = GoalDetailTodo(id="44444444-4444-4444-4444-444444444444", text="should not appear", done=False, sort_order=0)
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[update],
        todos=[todo],
        error="This goal isn't available.",
    )

    result = goal_detail_data_to_dict(data)

    assert result == {"error": "This goal isn't available."}
    assert "id" not in result
    assert "title" not in result
    assert "description" not in result
    assert "progressPercent" not in result
    assert "recentUpdates" not in result
    assert "todos" not in result


def test_goal_detail_data_to_dict_no_error_sets_error_key_to_none_explicitly():
    data = GoalDetailViewData(
        id="33333333-3333-3333-3333-333333333333",
        title="Run a 5k",
        description=None,
        progress_percent=None,
        recent_updates=[],
        todos=[],
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
        todos=[],
    )

    result = goal_detail_data_to_dict(data)

    assert "transcript" not in result
    for update_dict in result["recentUpdates"]:
        assert "transcript" not in update_dict
