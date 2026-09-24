import pytest

from pixelpilot.services.prompt_enhancer import (
    EDIT_MAX_NEW_TOKENS,
    IMAGE_MAX_PIXELS,
    T2I_MAX_NEW_TOKENS,
    T2I_PRESENCE_PENALTY,
    parse_enhancer_output,
)


def test_official_qwen_profiles_are_preserved():
    assert T2I_MAX_NEW_TOKENS == 16256
    assert EDIT_MAX_NEW_TOKENS == 24000
    assert T2I_PRESENCE_PENALTY == 1.5
    assert IMAGE_MAX_PIXELS == 1024 * 1024


def test_parse_enhancer_output_after_thinking():
    generated = (
        "<think>internal reasoning</think>"
        '{"rewritten_prompt":"A detailed cinematic scene","wh_ratio":"16:9"}'
    )
    prompt, ratio, ratio_follow = parse_enhancer_output(generated)
    assert prompt == "A detailed cinematic scene"
    assert ratio == "16:9"
    assert ratio_follow is None


def test_parse_enhancer_output_accepts_fenced_and_extra_text():
    generated = (
        "analysis</think>\n"
        "Result:\n```json\n"
        '{"rewritten_prompt":"Detailed edit","wh_ratio":"","ratio_follow":"<image1>"}'
        "\n```"
    )
    prompt, ratio, ratio_follow = parse_enhancer_output(
        generated,
        include_ratio_follow=True,
    )
    assert prompt == "Detailed edit"
    assert ratio is None
    assert ratio_follow == "<image1>"


def test_parse_enhancer_output_accepts_training_typo():
    prompt, ratio, ratio_follow = parse_enhancer_output(
        '{"rewrited_prompt":"Recovered prompt","wh_ratio":"4:3"}'
    )
    assert prompt == "Recovered prompt"
    assert ratio == "4:3"
    assert ratio_follow is None


def test_parse_enhancer_output_uses_last_valid_json_object():
    generated = (
        'note {"ignored":"object"} '
        '{"rewritten_prompt":"Final prompt","wh_ratio":"3:2"}'
    )
    prompt, ratio, _ = parse_enhancer_output(generated)
    assert prompt == "Final prompt"
    assert ratio == "3:2"


def test_parse_enhancer_output_rejects_missing_prompt():
    with pytest.raises(RuntimeError):
        parse_enhancer_output('{"wh_ratio":"1:1"}')
