from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pixelpilot.config import Settings


@dataclass(slots=True, frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_local_preflight(settings: Settings, *, repo_root: Path | None = None) -> list[Check]:
    _ = repo_root
    checks: list[Check] = []
    checks.append(Check("Telegram token", bool(settings.telegram_bot_token), "configured" if settings.telegram_bot_token else "missing"))
    checks.append(Check("Owner Telegram ID", settings.owner_telegram_id > 0, str(settings.owner_telegram_id or "missing")))
    checks.append(Check("Vast API key", bool(settings.vast_api_key), "configured" if settings.vast_api_key else "missing"))
    checks.append(Check("HF read token", True, "configured" if settings.hf_token else "optional; model is public"))
    source_ok = bool(settings.pixelpilot_repo_url or settings.vast_template_hash)
    checks.append(Check("Vast bootstrap source", source_ok, "repository URL configured" if settings.pixelpilot_repo_url else "template hash configured" if settings.vast_template_hash else "missing repo URL/template hash"))
    checks.append(Check("Model", bool(settings.model_id), settings.model_id or "missing"))
    checks.append(Check("Vast disk", settings.vast_disk_gb >= 60, f"{settings.vast_disk_gb} GB"))
    checks.append(Check("GPU VRAM policy", settings.vast_min_gpu_ram_gb >= 48, f">= {settings.vast_min_gpu_ram_gb} GB"))
    return checks


def _git_source_check(settings: Settings) -> Check:
    if settings.vast_template_hash and not settings.pixelpilot_repo_url:
        return Check("Git bootstrap source", True, "using Vast template")
    if not settings.pixelpilot_repo_url:
        return Check("Git bootstrap source", False, "repository URL missing")
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", settings.pixelpilot_repo_url, settings.pixelpilot_repo_ref],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        return Check("Git bootstrap source", False, "git executable not found")
    except subprocess.TimeoutExpired:
        return Check("Git bootstrap source", False, "git source check timed out")
    if result.returncode == 0:
        return Check("Git bootstrap source", True, f"ref {settings.pixelpilot_repo_ref} reachable")
    return Check("Git bootstrap source", False, f"ref unreachable (git exit {result.returncode})")


def _hf_access_check(settings: Settings) -> Check:
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url
        url = hf_hub_url(settings.model_id, "config.json")
        metadata = get_hf_file_metadata(url, token=settings.hf_token or None, timeout=15)
        size = int(metadata.size or 0)
        if size <= 0:
            return Check("Qwen Omni model access", False, "config metadata returned no size")
        return Check("Qwen Omni model access", True, f"{settings.model_id} reachable")
    except Exception as exc:
        return Check("Qwen Omni model access", False, f"metadata failed: {type(exc).__name__}")


async def run_external_preflight(settings: Settings) -> list[Check]:
    git_check, hf_check = await asyncio.gather(
        asyncio.to_thread(_git_source_check, settings),
        asyncio.to_thread(_hf_access_check, settings),
    )
    return [git_check, hf_check]


def format_preflight(checks: list[Check]) -> str:
    lines = ["🧪 <b>PixelPilot Preflight</b>", ""]
    for check in checks:
        icon = "✅" if check.ok else "❌"
        lines.append(f"{icon} <b>{check.name}</b>: {check.detail}")
    lines.append("")
    lines.append("النتيجة: <b>جاهز</b>" if all(x.ok for x in checks) else "النتيجة: <b>يوجد إعداد ناقص</b>")
    return "\n".join(lines)
