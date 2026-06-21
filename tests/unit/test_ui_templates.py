"""Unit tests for the home-view HTML renderer in `app.ui_templates`.

These exercise `render_home_view` directly against `HomeViewData`/
`HomeGoalCard` inputs with no DB/MCP/auth involved — see
`tests/unit/test_mcp_server.py` for the tool-logic layer that constructs
this data, and `tests/feature/test_mcp_get_home_view.py` for the
wire-protocol layer.
"""

from app.ui_templates import (
    GoalDetailUpdate,
    GoalDetailViewData,
    HomeGoalCard,
    HomeViewData,
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


def test_render_home_view_escapes_xss_payload_in_greeting_name():
    payload = "<script>alert(1)</script>"
    data = HomeViewData(greeting_name=payload, goals=[])

    html_output = render_home_view(data)

    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;script&gt;" in html_output


def test_render_home_view_escapes_xss_payload_in_goal_card_title():
    payload = "<script>alert(1)</script>"
    data = HomeViewData(greeting_name="Sam", goals=[_card(title=payload)])

    html_output = render_home_view(data)

    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;script&gt;" in html_output


def test_render_home_view_escapes_xss_payload_in_error_message():
    payload = "<script>alert(1)</script>"
    data = HomeViewData(greeting_name=None, goals=[], error=payload)

    html_output = render_home_view(data)

    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;script&gt;" in html_output


def test_render_home_view_renders_no_estimate_yet_for_none_progress_not_zero_percent():
    data = HomeViewData(greeting_name="Sam", goals=[_card(progress_percent=None)])

    html_output = render_home_view(data)
    body = html_output.split("<body>")[1]

    assert "0%" not in body
    assert "no-estimate" in body


def test_render_home_view_renders_real_percentage_text_for_numeric_progress():
    data = HomeViewData(greeting_name="Sam", goals=[_card(progress_percent=42)])

    html_output = render_home_view(data)

    assert "42%" in html_output


def test_render_home_view_renders_zero_percent_distinctly_from_no_estimate():
    data = HomeViewData(greeting_name="Sam", goals=[_card(progress_percent=0)])

    html_output = render_home_view(data)
    body = html_output.split("<body>")[1]

    assert "0%" in body
    assert "no-estimate" not in body


def test_render_home_view_shows_updated_line_when_last_updated_at_present():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[_card(last_updated_at="2026-06-15T10:00:00+00:00")],
    )

    html_output = render_home_view(data)

    assert "Updated" in html_output
    assert "2026-06-15" in html_output


def test_render_home_view_omits_updated_line_when_last_updated_at_is_none():
    data = HomeViewData(greeting_name="Sam", goals=[_card(last_updated_at=None)])

    html_output = render_home_view(data)

    assert "Updated" not in html_output


def test_render_home_view_empty_state_has_greeting_and_two_entries_no_cards():
    data = HomeViewData(greeting_name="Sam", goals=[])

    html_output = render_home_view(data)

    assert "Sam" in html_output
    assert "Create a new goal" in html_output
    assert "Just want to talk?" in html_output
    assert 'class="card"' not in html_output


def test_render_home_view_goals_state_has_one_card_per_goal():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[_card(id="11111111-1111-1111-1111-111111111111", title="Goal A"),
               _card(id="22222222-2222-2222-2222-222222222222", title="Goal B")],
    )

    html_output = render_home_view(data)

    assert html_output.count('class="card"') == 2
    assert "Goal A" in html_output
    assert "Goal B" in html_output


def test_render_home_view_failure_state_has_message_and_two_entries_no_cards():
    data = HomeViewData(greeting_name=None, goals=[], error="We couldn't load your home screen right now.")

    html_output = render_home_view(data)

    assert "We couldn&#x27;t load your home screen right now." in html_output or \
        "We couldn't load your home screen right now." in html_output
    assert "Create a new goal" in html_output
    assert "Just want to talk?" in html_output
    assert 'class="card"' not in html_output


def test_render_home_view_failure_state_takes_precedence_over_goals_and_empty_state():
    data = HomeViewData(
        greeting_name="Sam",
        goals=[_card()],
        error="boom",
    )

    html_output = render_home_view(data)

    assert 'class="card"' not in html_output
    assert "boom" in html_output


def test_render_home_view_has_no_tab_bar_markup():
    data = HomeViewData(greeting_name="Sam", goals=[_card()])

    html_output = render_home_view(data)

    lowered = html_output.lower()
    assert "tab-bar" not in lowered
    assert "reflect" not in lowered
    assert "journey" not in lowered


def test_render_home_view_has_no_streak_or_total_days_markup():
    data = HomeViewData(greeting_name="Sam", goals=[_card()])

    html_output = render_home_view(data)

    lowered = html_output.lower()
    assert "total days" not in lowered
    assert "current streak" not in lowered
    assert "streak" not in lowered


def test_create_goal_and_talk_entries_use_prompt_injection_not_tool_call():
    data = HomeViewData(greeting_name="Sam", goals=[])

    html_output = render_home_view(data)

    assert "lifecoachSendPrompt('I want to create a new goal.')" in html_output
    assert "lifecoachSendPrompt('I just want to talk.')" in html_output
    assert "lifecoachSendTool" not in html_output.split("function lifecoachSendTool")[1].split(
        "function lifecoachSendPrompt"
    )[0].replace("lifecoachSendTool(toolName, params)", "")


def test_goal_card_click_invokes_tool_call_with_goal_id_not_prompt():
    goal_id = "33333333-3333-3333-3333-333333333333"
    data = HomeViewData(greeting_name="Sam", goals=[_card(id=goal_id)])

    html_output = render_home_view(data)

    assert f"lifecoachSendTool('get_goal_detail_view', {{ goal_id: '{goal_id}' }})" in html_output


def test_script_includes_unverified_disclaimer_comments_for_both_postmessage_functions():
    data = HomeViewData(greeting_name="Sam", goals=[])

    html_output = render_home_view(data)

    tool_fn = html_output.split("function lifecoachSendTool")[1].split("function lifecoachSendPrompt")[0]
    prompt_fn = html_output.split("function lifecoachSendPrompt")[1]

    assert "UNVERIFIED" in tool_fn
    assert "UNVERIFIED" in prompt_fn


GOAL_ID = "33333333-3333-3333-3333-333333333333"


def _detail_data(**overrides):
    defaults = dict(
        id=GOAL_ID,
        title="Run a 5k",
        description="Train three times a week",
        progress_percent=42,
        recent_updates=[],
    )
    defaults.update(overrides)
    return GoalDetailViewData(**defaults)


def test_render_goal_detail_view_renders_title_description_progress_and_updates():
    update = GoalDetailUpdate(content="Ran 3 miles today", created_at="2026-06-15T10:00:00+00:00")
    data = _detail_data(recent_updates=[update])

    html_output = render_goal_detail_view(data)

    assert "Run a 5k" in html_output
    assert "Train three times a week" in html_output
    assert "42%" in html_output
    assert "Ran 3 miles today" in html_output
    assert "2026-06-15" in html_output


def test_render_goal_detail_view_never_includes_transcript_field_name():
    update = GoalDetailUpdate(content="Ran 3 miles today", created_at="2026-06-15T10:00:00+00:00")
    data = _detail_data(recent_updates=[update])

    html_output = render_goal_detail_view(data)

    assert "transcript" not in html_output.lower()


def test_render_goal_detail_view_renders_no_updates_yet_for_empty_recent_updates():
    data = _detail_data(recent_updates=[])

    html_output = render_goal_detail_view(data)

    assert "No updates yet." in html_output
    assert 'class="update-item"' not in html_output


def test_render_goal_detail_view_omits_description_block_when_none():
    data = _detail_data(description=None)

    html_output = render_goal_detail_view(data)
    body = html_output.split("<body>")[1]

    assert "detail-description" not in body


def test_render_goal_detail_view_renders_no_estimate_yet_for_none_progress_not_zero_percent():
    data = _detail_data(progress_percent=None)

    html_output = render_goal_detail_view(data)
    body = html_output.split("<body>")[1]

    assert "0%" not in body
    assert "no-estimate" in body


def test_render_goal_detail_view_renders_zero_percent_distinctly_from_no_estimate():
    data = _detail_data(progress_percent=0)

    html_output = render_goal_detail_view(data)
    body = html_output.split("<body>")[1]

    assert "0%" in body
    assert "no-estimate" not in body


def test_render_goal_detail_view_failure_state_has_message_and_no_title_or_updates():
    update = GoalDetailUpdate(content="should not appear", created_at="2026-06-15T10:00:00+00:00")
    data = GoalDetailViewData(
        id=None,
        title=None,
        description=None,
        progress_percent=None,
        recent_updates=[update],
        error="This goal isn't available.",
    )

    html_output = render_goal_detail_view(data)
    body = html_output.split("<body>")[1]

    assert "This goal isn&#x27;t available." in body or "This goal isn't available." in body
    assert 'id="goal-title-' not in body
    assert "should not appear" not in body
    assert "Continue this conversation" not in body
    assert "Delete goal" not in body


def test_render_goal_detail_view_failure_state_takes_precedence_over_content():
    data = _detail_data(error="boom")

    html_output = render_goal_detail_view(data)
    body = html_output.split("<body>")[1]

    assert 'id="goal-title-' not in body
    assert "boom" in body
    assert "Run a 5k" not in body


def test_render_goal_detail_view_continue_action_injects_prompt_not_tool_call():
    data = _detail_data()

    html_output = render_goal_detail_view(data)

    assert "lifecoachContinueGoal" in html_output
    assert "lifecoachSendPrompt" in html_output.split("function lifecoachContinueGoal")[1].split(
        "function lifecoachShowDeleteConfirm"
    )[0]


def test_render_goal_detail_view_delete_action_gated_behind_two_stage_confirm():
    data = _detail_data()

    html_output = render_goal_detail_view(data)

    assert 'class="delete-entry"' in html_output
    assert 'class="delete-confirm hidden"' in html_output
    assert f"lifecoachConfirmDelete('{GOAL_ID}')" in html_output
    assert 'lifecoachSendTool("delete_goal", { goal_id: goalId })' in html_output


def test_render_goal_detail_view_has_no_tab_bar_or_streak_markup():
    data = _detail_data()

    html_output = render_goal_detail_view(data)
    lowered = html_output.lower()

    assert "tab-bar" not in lowered
    assert "reflect" not in lowered
    assert "journey" not in lowered
    assert "total days" not in lowered
    assert "current streak" not in lowered
    assert "streak" not in lowered


def test_render_goal_detail_view_continue_button_onclick_contains_only_uuid_never_hostile_title_text():
    # Hostile title with a double-quote, a single-quote, and a raw <script>
    # tag. The "continue conversation" handler must read the title back
    # from escaped DOM text content at click-time (never interpolate free
    # text into the onclick JS string), so the onclick attribute itself
    # must contain nothing but the trusted UUID.
    hostile_title = '''Evil" Goal' <script>alert(1)</script>'''
    data = _detail_data(title=hostile_title)

    html_output = render_goal_detail_view(data)

    assert "<script>alert(1)</script>" not in html_output
    assert "&lt;script&gt;" in html_output

    onclick_marker = f"onclick=\"lifecoachContinueGoal('{GOAL_ID}')\""
    assert onclick_marker in html_output

    continue_button_start = html_output.index('class="continue-entry"')
    continue_button_end = html_output.index("</button>", continue_button_start)
    continue_button_markup = html_output[continue_button_start:continue_button_end]

    assert "onclick" in continue_button_markup
    onclick_start = continue_button_markup.index('onclick="') + len('onclick="')
    onclick_end = continue_button_markup.index('"', onclick_start)
    onclick_value = continue_button_markup[onclick_start:onclick_end]

    assert onclick_value == f"lifecoachContinueGoal('{GOAL_ID}')"
    assert "Evil" not in onclick_value
    assert "script" not in onclick_value.lower()
    assert "'" not in onclick_value.replace(f"'{GOAL_ID}'", "")


def test_render_goal_detail_view_delete_button_onclick_contains_only_uuid_never_hostile_title_text():
    hostile_title = '''Evil" Goal' <script>alert(1)</script>'''
    data = _detail_data(title=hostile_title)

    html_output = render_goal_detail_view(data)

    delete_show_marker = f"onclick=\"lifecoachShowDeleteConfirm('{GOAL_ID}')\""
    confirm_marker = f"onclick=\"lifecoachConfirmDelete('{GOAL_ID}')\""
    assert delete_show_marker in html_output
    assert confirm_marker in html_output
    assert "Evil" not in delete_show_marker
    assert "Evil" not in confirm_marker


def test_render_goal_detail_view_title_rendered_as_escaped_dom_text_not_inside_any_onclick():
    hostile_title = '''Evil" Goal' <script>alert(1)</script>'''
    data = _detail_data(title=hostile_title)

    html_output = render_goal_detail_view(data)

    title_node_marker = f'id="goal-title-{GOAL_ID}"'
    assert title_node_marker in html_output
    title_start = html_output.index(title_node_marker)
    title_tag_end = html_output.index(">", title_start) + 1
    title_close = html_output.index("</p>", title_tag_end)
    title_text_content = html_output[title_tag_end:title_close]

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in title_text_content
    assert "<script>" not in title_text_content

    for onclick_value in _all_onclick_values(html_output):
        assert "Evil" not in onclick_value
        assert "script" not in onclick_value.lower()


def _all_onclick_values(html_output: str) -> list[str]:
    values = []
    marker = 'onclick="'
    start = 0
    while True:
        idx = html_output.find(marker, start)
        if idx == -1:
            break
        value_start = idx + len(marker)
        value_end = html_output.index('"', value_start)
        values.append(html_output[value_start:value_end])
        start = value_end + 1
    return values


def test_html_escape_neutralizes_single_quote_in_interpolated_id():
    # The only value interpolated into a JS execution context (the onclick
    # attribute's single-quoted string) is the goal id, which is always a
    # server-generated UUID, never raw user input. This test documents that
    # html.escape's default quote=True behavior would HTML-entity-encode an
    # embedded single quote (preventing it from breaking out of the
    # surrounding HTML attribute), but flags that this alone would NOT fully
    # neutralize a JS-string-context breakout for an arbitrary untrusted
    # value, since the browser HTML-decodes the attribute before the
    # onclick handler's JS body executes — relevant only if a future change
    # ever interpolates a non-UUID, user-controlled value into this
    # template's onclick JS.
    import html as html_module

    assert html_module.escape("'") == "&#x27;"
