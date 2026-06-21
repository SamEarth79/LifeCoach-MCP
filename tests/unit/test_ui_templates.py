"""Unit tests for the home-view HTML renderer in `app.ui_templates`.

These exercise `render_home_view` directly against `HomeViewData`/
`HomeGoalCard` inputs with no DB/MCP/auth involved — see
`tests/unit/test_mcp_server.py` for the tool-logic layer that constructs
this data, and `tests/feature/test_mcp_get_home_view.py` for the
wire-protocol layer.
"""

from app.ui_templates import HomeGoalCard, HomeViewData, render_home_view


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
