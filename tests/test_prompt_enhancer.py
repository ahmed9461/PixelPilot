import pytest

from pixelpilot.services.prompt_enhancer import parse_enhancer_output


def test_parse_enhancer_output_after_thinking():
    generated = (
        "<think>internal reasoning</think>"
        '{"rewritten_prompt":"A detailed cinematic scene","wh_ratio":"16:9"}'
    )
    prompt, ratio = parse_enhancer_output(generated)
    assert prompt == "A detailed cinematic scene"
    assert ratio == "16:9"


def test_parse_enhancer_output_accepts_json_fence():
    generated = '```json\\n{"rewritten_prompt":"Detailed edit","wh_ratio":""}\\n```'
    prompt, ratio = parse_enhancer_output(generated)
    assert prompt == "Detailed edit"
    assert ratio is None


def test_parse_enhancer_output_rejects_missing_prompt():
    with pytest.raises(RuntimeError):
        parse_enhancer_output('{"wh_ratio":"1:1"}')