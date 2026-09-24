from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

TOKEN = os.environ.get("PIXELPILOT_INFERENCE_TOKEN", "")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen-Image-2.1")
MODEL_DTYPE = os.environ.get("MODEL_DTYPE", "bfloat16").strip().lower()
MEMORY_MODE = os.environ.get("IMAGE_MEMORY_MODE", "auto").strip().lower()
FULL_GPU_MIN_VRAM_GB = int(os.environ.get("IMAGE_FULL_GPU_MIN_VRAM_GB", "48"))
VAE_TILING = os.environ.get("IMAGE_VAE_TILING", "true").strip().lower() not in {"0", "false", "no"}
VAE_SLICING = os.environ.get("IMAGE_VAE_SLICING", "true").strip().lower() not in {"0", "false", "no"}
MAX_REFERENCE_IMAGES = int(os.environ.get("IMAGE_MAX_REFERENCE_IMAGES", "10"))
MAX_UPLOAD_BYTES = int(os.environ.get("IMAGE_MAX_UPLOAD_MB", "25")) * 1024 * 1024


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    width: int = 1024
    height: int = 1024
    num_inference_steps: int = 40
    seed: int | None = None
    true_cfg_scale: float = 1.0
    negative_prompt: str | None = None


@dataclass(slots=True)
class RuntimeState:
    pipe: Any | None = None
    torch: Any | None = None
    device: str = "unknown"
    memory_mode: str = "unknown"
    gpu_vram_gb: float = 0.0


state = RuntimeState()
generation_lock = asyncio.Lock()


def _check_auth(authorization: str | None) -> None:
    if not TOKEN:
        raise HTTPException(status_code=503, detail="Inference token is not configured")
    expected = f"Bearer {TOKEN}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_dimensions(width: int, height: int) -> None:
    for name, value in (("width", width), ("height", height)):
        if value < 256 or value > 3072 or value % 32 != 0:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must be between 256 and 3072 and divisible by 32",
            )


def _validate_steps(steps: int) -> None:
    if not 1 <= steps <= 80:
        raise HTTPException(status_code=422, detail="num_inference_steps must be between 1 and 80")


def _dtype(torch: Any) -> Any:
    if MODEL_DTYPE == "float16":
        return torch.float16
    return torch.bfloat16


def _load_pipeline() -> None:
    import torch
    from diffusers import QwenImage21Pipeline

    if not torch.cuda.is_available():
        raise RuntimeError("Qwen-Image-2.1 requires a CUDA GPU in this deployment")

    total_bytes = int(torch.cuda.get_device_properties(0).total_memory)
    total_gib = total_bytes / (1024**3)
    state.gpu_vram_gb = total_gib
    state.torch = torch

    logger.info(
        "Loading %s dtype=%s gpu_vram=%.1fGiB memory_mode=%s",
        MODEL_ID,
        MODEL_DTYPE,
        total_gib,
        MEMORY_MODE,
    )
    pipe = QwenImage21Pipeline.from_pretrained(
        MODEL_ID,
        torch_dtype=_dtype(torch),
    )
    pipe.set_progress_bar_config(disable=True)

    rounded_vram = int(round(total_gib))
    if MEMORY_MODE == "gpu":
        pipe.to("cuda")
        active_memory_mode = "gpu"
    elif MEMORY_MODE == "offload":
        pipe.enable_model_cpu_offload()
        active_memory_mode = "offload"
    elif MEMORY_MODE == "auto":
        if rounded_vram >= FULL_GPU_MIN_VRAM_GB:
            pipe.to("cuda")
            active_memory_mode = "gpu"
        else:
            pipe.enable_model_cpu_offload()
            active_memory_mode = "offload"
    else:
        raise RuntimeError(f"Unsupported IMAGE_MEMORY_MODE: {MEMORY_MODE}")

    if VAE_TILING and getattr(pipe, "vae", None) is not None:
        enable = getattr(pipe.vae, "enable_tiling", None)
        if callable(enable):
            enable()
    if VAE_SLICING and getattr(pipe, "vae", None) is not None:
        enable = getattr(pipe.vae, "enable_slicing", None)
        if callable(enable):
            enable()

    try:
        torch.backends.cuda.matmul.allow_tf32 = True
    except Exception:
        pass

    state.pipe = pipe
    state.device = "cuda"
    state.memory_mode = active_memory_mode
    logger.info(
        "Qwen-Image runtime ready: mode=%s gpu_vram=%.1fGiB",
        active_memory_mode,
        total_gib,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not TOKEN:
        raise RuntimeError("PIXELPILOT_INFERENCE_TOKEN is required")
    await asyncio.to_thread(_load_pipeline)
    yield
    state.pipe = None
    if state.torch is not None:
        try:
            state.torch.cuda.empty_cache()
        except Exception:
            pass


app = FastAPI(title="PixelPilot Qwen-Image Gateway", lifespan=lifespan)


def _generator(seed: int) -> Any:
    torch = state.torch
    if torch is None:
        raise RuntimeError("Torch runtime is unavailable")
    return torch.Generator(device="cuda").manual_seed(seed)


def _normalize_seed(seed: int | None) -> int:
    if seed is None:
        return secrets.randbelow(2_147_483_647)
    value = int(seed)
    if value < 0:
        raise HTTPException(status_code=422, detail="seed must be >= 0")
    return value


def _encode_png(image: Any) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _decode_uploaded_image(data: bytes) -> Any:
    from PIL import Image

    if not data:
        raise HTTPException(status_code=400, detail="Empty reference image")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Reference image is too large")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid reference image") from exc

    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def _run_pipeline(
    *,
    prompt: str,
    width: int,
    height: int,
    steps: int,
    seed: int,
    reference_images: list[Any],
    true_cfg_scale: float,
    negative_prompt: str | None,
) -> Any:
    pipe = state.pipe
    if pipe is None:
        raise RuntimeError("Image model is not loaded")

    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": steps,
        "generator": _generator(seed),
    }
    if reference_images:
        kwargs["image"] = reference_images[0] if len(reference_images) == 1 else reference_images
    if true_cfg_scale != 1.0:
        kwargs["true_cfg_scale"] = float(true_cfg_scale)
        if negative_prompt is not None:
            kwargs["negative_prompt"] = negative_prompt

    try:
        output = pipe(**kwargs)
        images = getattr(output, "images", None)
        if not images:
            raise RuntimeError("Pipeline returned no image")
        return images[0]
    finally:
        if state.torch is not None:
            try:
                state.torch.cuda.empty_cache()
            except Exception:
                pass


async def _generate_response(
    *,
    prompt: str,
    width: int,
    height: int,
    steps: int,
    seed: int | None,
    reference_images: list[Any],
    true_cfg_scale: float,
    negative_prompt: str | None,
) -> dict[str, Any]:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise HTTPException(status_code=422, detail="prompt cannot be empty")
    _validate_dimensions(width, height)
    _validate_steps(steps)
    if len(reference_images) > MAX_REFERENCE_IMAGES:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_REFERENCE_IMAGES} reference images are supported",
        )

    actual_seed = _normalize_seed(seed)
    async with generation_lock:
        try:
            image = await asyncio.to_thread(
                _run_pipeline,
                prompt=prompt,
                width=width,
                height=height,
                steps=steps,
                seed=actual_seed,
                reference_images=reference_images,
                true_cfg_scale=true_cfg_scale,
                negative_prompt=negative_prompt,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Image generation failed")
            detail = str(exc)
            if "out of memory" in detail.lower():
                detail = (
                    "GPU ran out of memory. Try Standard quality, fewer/lower-resolution "
                    "reference images, or a GPU with more VRAM."
                )
            raise HTTPException(status_code=500, detail=detail[:1000]) from exc

    return {
        "b64_json": _encode_png(image),
        "mime_type": "image/png",
        "seed": actual_seed,
        "width": width,
        "height": height,
        "model": MODEL_ID,
        "reference_count": len(reference_images),
    }


@app.get("/health")
async def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    if state.pipe is None:
        raise HTTPException(status_code=503, detail="Image model is loading")
    return {
        "status": "ok",
        "model": MODEL_ID,
        "device": state.device,
        "memory_mode": state.memory_mode,
        "gpu_vram_gb": round(state.gpu_vram_gb, 2),
        "max_reference_images": MAX_REFERENCE_IMAGES,
    }


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    if state.pipe is None:
        raise HTTPException(status_code=503, detail="Image model is loading")
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


@app.post("/v1/images/generations")
async def image_generations(
    request: GenerationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_auth(authorization)
    return await _generate_response(
        prompt=request.prompt,
        width=request.width,
        height=request.height,
        steps=request.num_inference_steps,
        seed=request.seed,
        reference_images=[],
        true_cfg_scale=request.true_cfg_scale,
        negative_prompt=request.negative_prompt,
    )


@app.post("/v1/images/edits")
async def image_edits(
    image: list[UploadFile] = File(...),
    prompt: str = Form(...),
    width: int = Form(1024),
    height: int = Form(1024),
    num_inference_steps: int = Form(40),
    seed: int | None = Form(None),
    true_cfg_scale: float = Form(1.0),
    negative_prompt: str | None = Form(None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_auth(authorization)
    if not image:
        raise HTTPException(status_code=422, detail="At least one reference image is required")
    if len(image) > MAX_REFERENCE_IMAGES:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_REFERENCE_IMAGES} reference images are supported",
        )

    reference_images: list[Any] = []
    for upload in image:
        mime = (upload.content_type or "").lower()
        if mime and not mime.startswith("image/"):
            raise HTTPException(status_code=415, detail="Only image references are supported")
        reference_images.append(_decode_uploaded_image(await upload.read()))

    return await _generate_response(
        prompt=prompt,
        width=width,
        height=height,
        steps=num_inference_steps,
        seed=seed,
        reference_images=reference_images,
        true_cfg_scale=true_cfg_scale,
        negative_prompt=negative_prompt,
    )
