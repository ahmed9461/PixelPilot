from pathlib import Path
import pytest

from pixelpilot.setup_env import render_env, validate_setup_values, write_private_env


def base_values() -> dict[str, str]:
    return {"TELEGRAM_BOT_TOKEN": "tg-secret", "OWNER_TELEGRAM_ID": "123456", "VAST_API_KEY": "vast-secret", "HF_TOKEN": "", "PIXELPILOT_REPO_URL": "https://example.invalid/PixelPilot.git", "VAST_TEMPLATE_HASH": ""}


def test_render_env_preserves_comments_and_replaces_keys():
    rendered = render_env("# comment\nA=old\nB=keep\n", {"A": "new", "C": "added"})
    assert "# comment" in rendered and "A=new" in rendered and "B=keep" in rendered and "C=added" in rendered


def test_validate_setup_requires_repo_or_template():
    values = base_values(); values["PIXELPILOT_REPO_URL"] = ""
    assert any("PIXELPILOT_REPO_URL or VAST_TEMPLATE_HASH" in item for item in validate_setup_values(values))


def test_validate_setup_accepts_template_mode_without_hf_token():
    values = base_values(); values["PIXELPILOT_REPO_URL"] = ""; values["VAST_TEMPLATE_HASH"] = "abc123"
    assert validate_setup_values(values) == []


def test_write_private_env_does_not_modify_template(tmp_path: Path):
    template = tmp_path / ".env.example"; target = tmp_path / ".env"
    template.write_text("TELEGRAM_BOT_TOKEN=\nOWNER_TELEGRAM_ID=0\nVAST_API_KEY=\nHF_TOKEN=\nPIXELPILOT_REPO_URL=\n", encoding="utf-8")
    original = template.read_text(encoding="utf-8")
    write_private_env(template, target, base_values())
    assert template.read_text(encoding="utf-8") == original
    body = target.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=tg-secret" in body and "OWNER_TELEGRAM_ID=123456" in body


def test_write_private_env_rejects_bad_owner_id(tmp_path: Path):
    template = tmp_path / ".env.example"; target = tmp_path / ".env"
    template.write_text("OWNER_TELEGRAM_ID=0\n", encoding="utf-8")
    values = base_values(); values["OWNER_TELEGRAM_ID"] = "not-a-number"
    with pytest.raises(ValueError):
        write_private_env(template, target, values)
