from pathlib import Path

import pytest

from pixelpilot.setup_env import render_env, validate_setup_values, write_private_env


def base_values() -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "tg-secret",
        "OWNER_TELEGRAM_ID": "123456",
        "VAST_API_KEY": "vast-secret",
        "HF_TOKEN": "hf-secret",
        "PIXELPILOT_REPO_URL": "https://example.invalid/PixelPilot.git",
        "VAST_TEMPLATE_HASH": "",
    }


def test_render_env_preserves_comments_and_replaces_keys():
    template = "# comment\nA=old\nB=keep\n"
    rendered = render_env(template, {"A": "new", "C": "added"})
    assert "# comment" in rendered
    assert "A=new" in rendered
    assert "B=keep" in rendered
    assert "C=added" in rendered


def test_validate_setup_requires_repo_or_template():
    values = base_values()
    values["PIXELPILOT_REPO_URL"] = ""
    errors = validate_setup_values(values)
    assert any("PIXELPILOT_REPO_URL or VAST_TEMPLATE_HASH" in item for item in errors)


def test_validate_setup_accepts_template_mode():
    values = base_values()
    values["PIXELPILOT_REPO_URL"] = ""
    values["VAST_TEMPLATE_HASH"] = "abc123"
    assert validate_setup_values(values) == []


def test_write_private_env_does_not_modify_template(tmp_path: Path):
    template = tmp_path / ".env.example"
    target = tmp_path / ".env"
    template.write_text("TELEGRAM_BOT_TOKEN=\nOWNER_TELEGRAM_ID=0\nVAST_API_KEY=\nHF_TOKEN=\nPIXELPILOT_REPO_URL=\n", encoding="utf-8")
    original = template.read_text(encoding="utf-8")
    write_private_env(template, target, base_values())
    assert template.read_text(encoding="utf-8") == original
    body = target.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=tg-secret" in body
    assert "OWNER_TELEGRAM_ID=123456" in body


def test_write_private_env_rejects_bad_owner_id(tmp_path: Path):
    template = tmp_path / ".env.example"
    target = tmp_path / ".env"
    template.write_text("OWNER_TELEGRAM_ID=0\n", encoding="utf-8")
    values = base_values()
    values["OWNER_TELEGRAM_ID"] = "not-a-number"
    with pytest.raises(ValueError):
        write_private_env(template, target, values)
