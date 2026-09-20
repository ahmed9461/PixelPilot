from pixelpilot.bot.routers.settings import (
    _generation_keyboard,
    _group_keyboard,
    _prompt_actions,
    _prompts_keyboard,
)


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_group_prompt_editor_remembers_group_origin():
    callbacks = _callbacks(_group_keyboard("tone", "balanced"))
    assert "assistant:prompt:open:tone:group" in callbacks


def test_prompt_hub_editor_remembers_hub_origin():
    callbacks = _callbacks(_prompts_keyboard())
    assert "assistant:prompt:open:tone:hub" in callbacks
    assert "assistant:prompt:open:persona:hub" in callbacks


def test_prompt_back_button_returns_to_the_screen_it_came_from():
    group_callbacks = _callbacks(_prompt_actions("tone", "direct", origin="group"))
    hub_callbacks = _callbacks(_prompt_actions("tone", "direct", origin="hub"))
    assert group_callbacks[-1] == "assistant:group:tone"
    assert hub_callbacks[-1] == "assistant:prompts"


def test_generation_value_buttons_are_noop_instead_of_reediting_same_screen():
    state = {
        "creativity_pct": 30,
        "diversity_pct": 80,
        "response_length_pct": 100,
        "repetition_guard_pct": 0,
    }
    keyboard = _generation_keyboard(state)
    center_callbacks = [row[1].callback_data for row in keyboard.inline_keyboard[:4]]
    assert center_callbacks == ["assistant:noop", "assistant:noop", "assistant:noop", "assistant:noop"]
