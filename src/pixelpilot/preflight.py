from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pixelpilot.config import Settings
from pixelpilot.workflow import load_workflow


@dataclass(slots=True, frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_local_preflight(settings: Settings, *, repo_root: Path | None = None) -> list[Check]:
    root = repo_root or Path(__file__).resolve().parents[2]
    checks: list[Check] = []

    checks.append(Check("Telegram token", bool(settings.telegram_bot_token), "configured" if settings.telegram_bot_token else "missing"))
    checks.append(Check("Owner Telegram ID", settings.owner_telegram_id > 0, str(settings.owner_telegram_id or "missing")))
    checks.append(Check("Vast API key", bool(settings.vast_api_key), "configured" if settings.vast_api_key else "missing"))
    checks.append(Check("HF read token", bool(settings.hf_token), "configured" if settings.hf_token else "missing"))
    source_ok = bool(settings.pixelpilot_repo_url or settings.vast_template_hash)
    checks.append(
        Check(
            "Vast bootstrap source",
            source_ok,
            "repository URL configured" if settings.pixelpilot_repo_url else "template hash configured" if settings.vast_template_hash else "missing repo URL/template hash",
        )
    )

    workflow_path = settings.workflow_path
    if not workflow_path.is_absolute():
        workflow_path = root / workflow_path
    try:
        load_workflow(workflow_path)
        checks.append(Check("Krea API workflow", True, str(workflow_path)))
    except Exception as exc:
        checks.append(Check("Krea API workflow", False, str(exc)))

    manifest_path = root / "resources/model_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = {item["filename"] for item in manifest.get("files", [])}
        expected = {"flux1-krea-dev.safetensors", "ae.safetensors", "clip_l.safetensors", "t5xxl_fp16.safetensors"}
        ok = names == expected
        checks.append(Check("Model manifest", ok, f"{len(names)} files" if ok else f"unexpected files: {sorted(names)}"))
    except Exception as exc:
        checks.append(Check("Model manifest", False, str(exc)))

    disk_ok = settings.vast_disk_gb >= 70
    checks.append(Check("Vast disk", disk_ok, f"{settings.vast_disk_gb} GB"))
    checks.append(Check("GPU VRAM policy", settings.vast_min_gpu_ram_gb >= 24, f">= {settings.vast_min_gpu_ram_gb} GB"))
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
    if not settings.hf_token:
        return Check("Krea gated access", False, "HF_TOKEN missing")
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url

        # HEAD/metadata only: verifies authorization to the gated file without downloading 23+ GB.
        url = hf_hub_url("black-forest-labs/FLUX.1-Krea-dev", "flux1-krea-dev.safetensors")
        metadata = get_hf_file_metadata(url, token=settings.hf_token, timeout=15)
        size = int(metadata.size or 0)
        if size <= 0:
            return Check("Krea gated access", False, "authorized metadata returned no file size")
        return Check("Krea gated access", True, f"authorized ({size / 1_000_000_000:.1f} GB checkpoint)")
    except Exception as exc:
        # Do not include the token or raw request URL in diagnostics.
        return Check("Krea gated access", False, f"authorization/metadata failed: {type(exc).__name__}")


async def run_external_preflight(settings: Settings) -> list[Check]:
    """Network checks that prevent renting a GPU with a broken source/token setup."""
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
