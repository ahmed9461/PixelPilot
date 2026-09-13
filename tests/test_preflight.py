from pathlib import Path

from pixelpilot.config import Settings
from pixelpilot.preflight import run_local_preflight


def test_preflight_passes_project_files(tmp_path):
    settings = Settings(
        _env_file=None,
        telegram_bot_token="t",
        owner_telegram_id=1,
        vast_api_key="v",
        hf_token="h",
        pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
        workflow_path=Path("resources/workflows/flux_krea_api.json"),
    )
    checks = run_local_preflight(settings, repo_root=Path.cwd())
    assert all(check.ok for check in checks)


def test_external_preflight_aggregates_checks(monkeypatch):
    import asyncio
    import pixelpilot.preflight as module
    from pixelpilot.preflight import Check

    settings = Settings(_env_file=None)
    monkeypatch.setattr(module, "_git_source_check", lambda settings: Check("git", True, "ok"))
    monkeypatch.setattr(module, "_hf_access_check", lambda settings: Check("hf", True, "ok"))
    checks = asyncio.run(module.run_external_preflight(settings))
    assert [x.name for x in checks] == ["git", "hf"]
    assert all(x.ok for x in checks)
