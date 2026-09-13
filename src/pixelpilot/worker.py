from __future__ import annotations

import hmac
import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from pixelpilot.domain import GenerationSpec
from pixelpilot.services.comfy_client import ComfyClient, ComfyError
from pixelpilot.workflow import build_flux_krea_workflow, load_workflow

app = FastAPI(title="PixelPilot Worker", version="0.3.0")

WORKER_TOKEN = os.environ.get("PIXELPILOT_WORKER_TOKEN", "")
TRUST_PROXY = os.environ.get("PIXELPILOT_TRUST_PROXY", "0").lower() in {"1", "true", "yes"}
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
REPO_ROOT = Path(os.environ.get("PIXELPILOT_ROOT", Path(__file__).resolve().parents[2]))
WORKFLOW_PATH = Path(os.environ.get("WORKFLOW_PATH", REPO_ROOT / "resources/workflows/flux_krea_api.json"))
MAX_BATCH = int(os.environ.get("GENERATION_MAX_BATCH", "4"))
MAX_STEPS = int(os.environ.get("GENERATION_MAX_STEPS", "40"))

EXPECTED_MODELS = {
    "diffusion_models": {"flux1-krea-dev.safetensors"},
    "text_encoders": {"clip_l.safetensors", "t5xxl_fp16.safetensors"},
    "vae": {"ae.safetensors"},
}

comfy = ComfyClient(COMFY_URL)
base_workflow = load_workflow(WORKFLOW_PATH)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int = Field(default=0, ge=0, le=2**63 - 1)
    steps: int = Field(default=20, ge=1)
    batch_size: int = Field(default=1, ge=1)
    preset: str = Field(default="natural", max_length=64)
    filename_prefix: str = Field(default="PixelPilot", min_length=1, max_length=128)

    @field_validator("width", "height")
    @classmethod
    def divisible_by_16(cls, value: int) -> int:
        if value % 16:
            raise ValueError("must be divisible by 16")
        return value

    @field_validator("steps")
    @classmethod
    def steps_limit(cls, value: int) -> int:
        if value > MAX_STEPS:
            raise ValueError(f"steps cannot exceed {MAX_STEPS}")
        return value

    @field_validator("batch_size")
    @classmethod
    def batch_limit(cls, value: int) -> int:
        if value > MAX_BATCH:
            raise ValueError(f"batch_size cannot exceed {MAX_BATCH}")
        return value


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    # When deployed behind Vast base-image Caddy, Caddy authenticates OPEN_BUTTON_TOKEN
    # and this worker binds only to localhost. Direct deployments keep this extra check.
    if TRUST_PROXY:
        return
    if not WORKER_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Worker token not configured")
    expected = f"Bearer {WORKER_TOKEN}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def model_state() -> tuple[bool, dict[str, list[str]]]:
    missing: dict[str, list[str]] = {}
    for folder, expected in EXPECTED_MODELS.items():
        try:
            present = set(await comfy.models(folder))
        except Exception:
            return False, {"api": [folder]}
        absent = sorted(expected.difference(present))
        if absent:
            missing[folder] = absent
    return not missing, missing


@app.get("/health")
async def health(_: None = Depends(require_token)) -> dict[str, object]:
    ready = await comfy.is_ready()
    models_ready = False
    missing: dict[str, list[str]] = {}
    if ready:
        models_ready, missing = await model_state()
    return {"ok": True, "comfy_ready": ready, "models_ready": models_ready, "missing_models": missing}


@app.get("/system")
async def system(_: None = Depends(require_token)) -> dict[str, object]:
    if not await comfy.is_ready():
        raise HTTPException(status_code=503, detail="ComfyUI not ready")
    return await comfy.system_stats()


@app.post("/jobs")
async def submit_job(request: GenerateRequest, _: None = Depends(require_token)) -> dict[str, str]:
    if not await comfy.is_ready():
        raise HTTPException(status_code=503, detail="ComfyUI not ready")
    models_ready, missing = await model_state()
    if not models_ready:
        raise HTTPException(status_code=503, detail={"missing_models": missing})
    spec = GenerationSpec(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
        seed=request.seed,
        steps=request.steps,
        batch_size=request.batch_size,
        preset=request.preset,
    )
    workflow = build_flux_krea_workflow(base_workflow, spec, filename_prefix=request.filename_prefix)
    try:
        prompt_id = await comfy.submit(workflow, client_id=f"pixelpilot-{uuid.uuid4().hex}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI submit failed: {exc}") from exc
    return {"prompt_id": prompt_id}


@app.get("/jobs/{prompt_id}")
async def job_status(prompt_id: str, _: None = Depends(require_token)) -> dict[str, Any]:
    try:
        return await comfy.job_status(prompt_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ComfyUI history failed: {exc}") from exc


@app.get("/images")
async def image(
    filename: str = Query(min_length=1, max_length=512),
    subfolder: str = Query(default="", max_length=512),
    type: str = Query(default="output", pattern="^(output|input|temp)$"),
    _: None = Depends(require_token),
) -> Response:
    try:
        content = await comfy.download_image(filename, subfolder, type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image download failed: {exc}") from exc
    media_type = "image/png" if filename.lower().endswith(".png") else "application/octet-stream"
    return Response(content=content, media_type=media_type)
