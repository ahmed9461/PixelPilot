from pathlib import Path
import importlib.util

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


def _load_migration_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_economy_profile.py"
    spec = importlib.util.spec_from_file_location("migrate_economy_profile", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_economy_migration_preserves_secrets_and_updates_only_profile_values():
    module = _load_migration_module()
    original = (
        "TELEGRAM_BOT_TOKEN=tg-secret\n"
        "VAST_API_KEY=vast-secret\n"
        "HF_TOKEN=hf-secret\n"
        "MODEL_ID=Qwen/Qwen3-Omni-30B-A3B-Instruct\n"
        "VAST_MIN_GPU_RAM_GB=80\n"
        "VAST_DISK_GB=150\n"
    )
    updated = module.update_env_text(original)
    assert "TELEGRAM_BOT_TOKEN=tg-secret" in updated
    assert "VAST_API_KEY=vast-secret" in updated
    assert "HF_TOKEN=hf-secret" in updated
    assert "MODEL_ID=Qwen/Qwen2.5-Omni-7B" in updated
    assert "VAST_MIN_GPU_RAM_GB=48" in updated
    assert "VAST_DISK_GB=80" in updated
    assert "VAST_MAX_PRICE_USD_HOUR=0.80" in updated


def test_economy_migration_creates_backup(tmp_path: Path):
    module = _load_migration_module()
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=secret\nMODEL_ID=old\n", encoding="utf-8")
    backup = module.migrate(env_path)
    assert backup.exists()
    assert "MODEL_ID=old" in backup.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=secret" in env_path.read_text(encoding="utf-8")
    assert "MODEL_ID=Qwen/Qwen2.5-Omni-7B" in env_path.read_text(encoding="utf-8")
