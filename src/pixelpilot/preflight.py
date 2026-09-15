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
    # The Comfy-Org FLUX.2 quantized files are public. Keep accepting HF_TOKEN
    # when configured, but do not block renting merely because it is absent.
    checks.append(Check("HF read token", True, "configured" if settings.hf_token else "optional for FLUX.2 profile"))
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
        checks.append(Check("FLUX.2 API workflow", True, str(workflow_path)))
    except Exception as exc:
        checks.append(Check("FLUX.2 API workflow", False, str(exc)))

    manifest_path = root / "resources/model_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        names = {item.get("target_name") or Path(item["filename"]).name for item in manifest.get("files", [])}
        expected = {
            "flux2_dev_fp8mixed.safetensors",
            "mistral_3_small_flux2_fp8.safetensors",
            "flux2-vae.safetensors",
        }
        ok = names == expected
        checks.append(Check("Model manifest", ok, f"{len(names)} files" if ok else f"unexpected files: {sorted(names)}"))
    except Exception as exc:
        checks.append(Check("Model manifest", False, str(exc)))

    disk_ok = settings.vast_disk_gb >= 70
    checks.append(Check("Vast disk", disk_ok, f"{settings.vast_disk_gb} GB"))
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

        filename = "split_files/diffusion_models/flux2_dev_fp8mixed.safetensors"
        url = hf_hub_url("Comfy-Org/flux2-dev", filename)
        metadata = get_hf_file_metadata(url, token=settings.hf_token or None, timeout=15)
        size = int(metadata.size or 0)
        if size <= 0:
            return Check("FLUX.2 model access", False, "metadata returned no file size")
        return Check("FLUX.2 model access", True, f"reachable ({size / 1_000_000_000:.1f} GB checkpoint)")
    except Exception as exc:
        return Check("FLUX.2 model access", False, f"metadata failed: {type(exc).__name__}")


async def run_external_preflight(settings: Settings) -> list[Check]:
    """Network checks that prevent renting a GPU with a broken source/model setup."""
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
