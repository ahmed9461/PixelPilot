from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from html import escape

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
    checks.append(Check("Chat/vision model", bool(settings.chat_model_id), settings.chat_model_id or "missing"))
    checks.append(Check("Worker transport", True, "HTTPS with certificate verification" if settings.inference_use_https and settings.inference_verify_tls else "WARNING: HTTP or unverified TLS; use a trusted tunnel for private media"))
    checks.append(Check("Image model", settings.model_id == "Qwen/Qwen-Image-2.1", settings.model_id or "missing"))
    checks.append(Check("Vast disk", settings.vast_disk_gb >= 70, f"{settings.vast_disk_gb} GB"))
    checks.append(Check("GPU VRAM minimum", settings.vast_min_gpu_ram_gb >= 24, f">= {settings.vast_min_gpu_ram_gb} GB"))
    checks.append(Check("Preferred GPU VRAM", settings.vast_preferred_gpu_ram_gb >= 48, f">= {settings.vast_preferred_gpu_ram_gb} GB"))
    checks.append(Check("Host RAM for offload", settings.vast_min_cpu_ram_gb >= 48, f">= {settings.vast_min_cpu_ram_gb} GB on offload GPUs"))
    checks.append(Check("Cancel unavailable asks", settings.vast_cancel_unavailable, "enabled" if settings.vast_cancel_unavailable else "must be true for safe rental"))
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


def _hf_access_check(settings: Settings, *, chat: bool = False) -> Check:
    model_id = settings.chat_model_id if chat else settings.model_id
    label = "Chat/vision model access" if chat else "Qwen-Image model access"
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url

        url = hf_hub_url(model_id, "config.json" if chat else "model_index.json")
        metadata = get_hf_file_metadata(url, token=settings.hf_token or None, timeout=15)
        size = int(metadata.size or 0)
        if size <= 0:
            return Check(label, False, "model metadata returned no size")
        return Check(label, True, f"{model_id} reachable")
    except Exception as exc:
        return Check(label, False, f"metadata failed: {type(exc).__name__}")


async def run_external_preflight(settings: Settings) -> list[Check]:
    git_check, hf_check, chat_check = await asyncio.gather(
        asyncio.to_thread(_git_source_check, settings),
        asyncio.to_thread(_hf_access_check, settings),
        asyncio.to_thread(_hf_access_check, settings, chat=True),
    )
    return [git_check, hf_check, chat_check]


def format_preflight(checks: list[Check]) -> str:
    lines = ["🧪 <b>PixelPilot Preflight</b>", ""]
    for check in checks:
        icon = "✅" if check.ok else "❌"
        lines.append(f"{icon} <b>{escape(check.name)}</b>: {escape(check.detail)}")
    lines.append("")
    lines.append("النتيجة: <b>جاهز</b>" if all(x.ok for x in checks) else "النتيجة: <b>يوجد إعداد ناقص</b>")
    return "\n".join(lines)
