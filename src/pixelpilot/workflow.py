from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pixelpilot.domain import GenerationSpec


class WorkflowError(RuntimeError):
    pass


NODE_UNET = "1"
NODE_CLIP = "2"
NODE_VAE = "3"
NODE_PROMPT = "4"
NODE_GUIDANCE = "5"
NODE_LATENT = "6"
NODE_NOISE = "7"
NODE_SAMPLER_SELECT = "8"
NODE_SCHEDULER = "9"
NODE_GUIDER = "10"
NODE_SAMPLER = "11"
NODE_DECODE = "12"
NODE_SAVE = "13"

QUALITY_BALANCED = "flux2_balanced"
QUALITY_MAX = "flux2_quality"
# Old profile names remain accepted so historical generations can still be
# re-run after upgrading the controller. They use the FLUX.2 workflow now.
LEGACY_PROFILES = {"official", "krea_quality"}
QUALITY_PROFILES = {QUALITY_BALANCED, QUALITY_MAX, *LEGACY_PROFILES}
FLUX2_GUIDANCE = 4.0


def load_workflow(path: str | Path) -> dict[str, Any]:
    workflow = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        NODE_UNET,
        NODE_CLIP,
        NODE_VAE,
        NODE_PROMPT,
        NODE_GUIDANCE,
        NODE_LATENT,
        NODE_NOISE,
        NODE_SAMPLER_SELECT,
        NODE_SCHEDULER,
        NODE_GUIDER,
        NODE_SAMPLER,
        NODE_DECODE,
        NODE_SAVE,
    }
    missing = required.difference(workflow)
    if missing:
        raise WorkflowError(f"Workflow missing nodes: {sorted(missing)}")
    return workflow


def build_flux2_workflow(
    base_workflow: dict[str, Any],
    spec: GenerationSpec,
    *,
    filename_prefix: str,
) -> dict[str, Any]:
    if not spec.prompt.strip():
        raise WorkflowError("Prompt cannot be empty")
    if spec.width % 16 or spec.height % 16:
        raise WorkflowError("Width and height must be divisible by 16")
    if spec.batch_size < 1:
        raise WorkflowError("batch_size must be >= 1")
    if spec.steps < 1:
        raise WorkflowError("steps must be >= 1")
    if spec.quality_profile not in QUALITY_PROFILES:
        raise WorkflowError(f"Unknown quality profile: {spec.quality_profile}")

    wf = copy.deepcopy(base_workflow)

    # Absolute rule: the text sent by the user is the text encoded by FLUX.2.
    # PixelPilot never trims, rewrites, translates, expands, or appends to it.
    wf[NODE_PROMPT]["inputs"]["text"] = spec.prompt
    wf[NODE_GUIDANCE]["inputs"]["guidance"] = FLUX2_GUIDANCE
    wf[NODE_LATENT]["inputs"].update(
        {"width": spec.width, "height": spec.height, "batch_size": spec.batch_size}
    )
    wf[NODE_NOISE]["inputs"]["noise_seed"] = spec.seed
    wf[NODE_SCHEDULER]["inputs"].update(
        {"steps": spec.steps, "width": spec.width, "height": spec.height}
    )
    wf[NODE_SAVE]["inputs"]["filename_prefix"] = filename_prefix
    return wf


# Compatibility alias for code or historical tests importing the old name.
# It intentionally builds the FLUX.2 workflow; Krea is no longer used.
build_flux_krea_workflow = build_flux2_workflow


def extract_history_images(history_item: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    outputs = history_item.get("outputs") or {}
    if not isinstance(outputs, dict):
        return images
    for node in outputs.values():
        if not isinstance(node, dict):
            continue
        for image in node.get("images") or []:
            if not isinstance(image, dict) or not image.get("filename"):
                continue
            images.append(
                {
                    "filename": str(image["filename"]),
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
            )
    return images


def history_error(history_item: dict[str, Any]) -> str | None:
    status = history_item.get("status") or {}
    if not isinstance(status, dict):
        return None
    status_str = str(status.get("status_str") or "").lower()
    if status_str not in {"error", "failed"}:
        return None
    messages = status.get("messages") or []
    return str(messages[-1] if messages else "ComfyUI generation failed")
