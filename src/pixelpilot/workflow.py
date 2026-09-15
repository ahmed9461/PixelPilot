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
NODE_LATENT = "5"
NODE_NEGATIVE = "6"
NODE_SAMPLER = "7"
NODE_DECODE = "8"
NODE_SAVE = "9"
NODE_FLUX_GUIDANCE = "10"

QUALITY_OFFICIAL = "official"
QUALITY_KREA = "krea_quality"
QUALITY_PROFILES = {QUALITY_OFFICIAL, QUALITY_KREA}
KREA_GUIDANCE = 4.5


def load_workflow(path: str | Path) -> dict[str, Any]:
    workflow = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {NODE_UNET, NODE_CLIP, NODE_VAE, NODE_PROMPT, NODE_LATENT, NODE_NEGATIVE, NODE_SAMPLER, NODE_DECODE, NODE_SAVE}
    missing = required.difference(workflow)
    if missing:
        raise WorkflowError(f"Workflow missing nodes: {sorted(missing)}")
    return workflow


def build_flux_krea_workflow(
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

    # PixelPilot never rewrites, decorates, expands, translates, trims, or
    # appends to the user's prompt. Only sampling parameters may change.
    wf[NODE_PROMPT]["inputs"]["text"] = spec.prompt
    wf[NODE_LATENT]["inputs"].update(
        {"width": spec.width, "height": spec.height, "batch_size": spec.batch_size}
    )
    wf[NODE_SAMPLER]["inputs"].update({"seed": spec.seed, "steps": spec.steps})

    if spec.quality_profile == QUALITY_KREA:
        # Krea's reference inference uses a guidance embedding around 4.5.
        # In ComfyUI this is FluxGuidance on the positive conditioning; KSampler
        # CFG remains 1.0 for FLUX. This leaves the prompt text untouched.
        wf[NODE_FLUX_GUIDANCE] = {
            "inputs": {
                "conditioning": [NODE_PROMPT, 0],
                "guidance": KREA_GUIDANCE,
            },
            "class_type": "FluxGuidance",
            "_meta": {"title": "Krea Guidance"},
        }
        wf[NODE_SAMPLER]["inputs"]["positive"] = [NODE_FLUX_GUIDANCE, 0]
    else:
        wf.pop(NODE_FLUX_GUIDANCE, None)
        wf[NODE_SAMPLER]["inputs"]["positive"] = [NODE_PROMPT, 0]

    wf[NODE_SAVE]["inputs"]["filename_prefix"] = filename_prefix
    return wf


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
