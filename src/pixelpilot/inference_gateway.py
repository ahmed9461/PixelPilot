from __future__ import annotations

import asyncio
import base64
import gc
import io
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from pixelpilot.services.prompt_enhancer import PromptEnhancement, enhance_i2i, enhance_t2i
from pixelpilot.services.vision_runtime import load_chat_model, run_chat
from pixelpilot.services.model_cache import prepare_model, phase, status as cache_status


logger = logging.getLogger(__name__)

TOKEN = os.environ.get("PIXELPILOT_INFERENCE_TOKEN", "")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen-Image-2.1")
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "Qwen/Qwen3.5-9B")
CHAT_MAX_IMAGES = int(os.environ.get("CHAT_MAX_IMAGES", "3"))
MODEL_DTYPE = os.environ.get("MODEL_DTYPE", "bfloat16").strip().lower()
MEMORY_MODE = os.environ.get("IMAGE_MEMORY_MODE", "auto").strip().lower()
FULL_GPU_MIN_VRAM_GB = int(os.environ.get("IMAGE_FULL_GPU_MIN_VRAM_GB", "48"))
VAE_TILING = os.environ.get("IMAGE_VAE_TILING", "true").strip().lower() not in {"0", "false", "no"}
VAE_SLICING = os.environ.get("IMAGE_VAE_SLICING", "true").strip().lower() not in {"0", "false", "no"}
MAX_REFERENCE_IMAGES = int(os.environ.get("IMAGE_MAX_REFERENCE_IMAGES", "10"))
MAX_UPLOAD_BYTES = int(os.environ.get("IMAGE_MAX_UPLOAD_MB", "25")) * 1024 * 1024
PE_T2I_ID = os.environ.get("PROMPT_ENHANCER_T2I_ID", "Qwen/Qwen-Image-2.1-PE-T2I")
PE_I2I_ID = os.environ.get("PROMPT_ENHANCER_I2I_ID", "Qwen/Qwen-Image-2.1-PE-I2I")


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    width: int = 1024
    height: int = 1024
    num_inference_steps: int = 40
    seed: int | None = None
    true_cfg_scale: float = 1.0
    negative_prompt: str | None = None
    enhance_prompt: bool = False


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    images: list[str] = Field(default_factory=list, max_length=3)
    max_new_tokens: int = Field(default=384, ge=32, le=1024)


@dataclass(slots=True)
class RuntimeState:
    pipe: Any | None = None
    chat_model: Any | None = None
    chat_processor: Any | None = None
    active_model: str = "none"
    torch: Any | None = None
    device: str = "unknown"
    memory_mode: str = "unknown"
    gpu_vram_gb: float = 0.0


state = RuntimeState()
generation_lock = asyncio.Lock()

async def _blocking(function, *args, **kwargs):
    # Cancelling an HTTP coroutine cannot stop a CUDA/download thread. Keep
    # the model-switch lock held until that thread actually finishes.
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try: return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise

enhancer_ready: set[str] = set()
enhancer_downloads: dict[str, asyncio.Task[None]] = {}


async def _download_enhancer(model_id: str) -> None:
    # Called only after an explicit enhanced image request, never on startup.
    # Downloading weights does not load the model onto the GPU.
    try:
        from huggingface_hub import snapshot_download
        await _blocking(snapshot_download, model_id)
    except Exception:
        logger.exception("Could not download requested prompt enhancer %s", model_id)
    else:
        enhancer_ready.add(model_id)
        logger.info("Prompt enhancer cached: %s", model_id)


def _ensure_enhancer_download(model_id: str) -> None:
    if model_id in enhancer_ready or model_id in enhancer_downloads:
        return
    task = asyncio.create_task(_download_enhancer(model_id), name="qwen-requested-enhancer-download")
    enhancer_downloads[model_id] = task

    def release(done: asyncio.Task[None]) -> None:
        if enhancer_downloads.get(model_id) is done:
            enhancer_downloads.pop(model_id, None)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(release)


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
        prepare_model(MODEL_ID),
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
    state.active_model = "image"
    state.device = "cuda"
    state.memory_mode = active_memory_mode
    phase("ready", MODEL_ID, error=None)
    logger.info(
        "Qwen-Image runtime ready: mode=%s gpu_vram=%.1fGiB",
        active_memory_mode,
        total_gib,
    )


def _release_gpu() -> None:
    gc.collect()
    if state.torch is not None:
        state.torch.cuda.empty_cache()


def _switch_to_chat() -> None:
    if state.chat_model is not None:
        return
    state.pipe = None
    state.active_model = "loading-chat"
    _release_gpu()
    import torch
    model, processor = load_chat_model(CHAT_MODEL_ID)
    state.torch = torch
    state.chat_model = model
    state.chat_processor = processor
    state.active_model = "chat"
    state.device = "cuda"
    state.gpu_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    phase("ready", CHAT_MODEL_ID, error=None)


def _switch_to_image() -> None:
    if state.pipe is not None:
        return
    state.chat_model = None
    state.chat_processor = None
    state.active_model = "loading-image"
    _release_gpu()
    _load_pipeline()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not TOKEN:
        raise RuntimeError("PIXELPILOT_INFERENCE_TOKEN is required")
    # Chat is immediately available. The (much larger) image pipeline only
    # loads after the first image request, avoiding duplicate model residency.
    async def warmup():
        async with generation_lock:
            try: await _blocking(_switch_to_chat)
            except Exception as exc:
                state.active_model = "failed-chat"
                phase("failed", CHAT_MODEL_ID, error=type(exc).__name__ + ": model startup failed; cache retained")
                logger.exception("Chat startup failed")
    startup = asyncio.create_task(warmup(), name="pixelpilot-chat-warmup")
    try:
        yield
    finally:
        tasks = (startup, *enhancer_downloads.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        enhancer_downloads.clear()
        state.pipe = None
        state.chat_model = None
        state.chat_processor = None
        state.active_model = "none"
        _release_gpu()


app = FastAPI(title="PixelPilot Multimodal Gateway", lifespan=lifespan)


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
        if image.width * image.height > 25_000_000:
            raise HTTPException(status_code=413, detail="Image pixel dimensions too large")
        from PIL import ImageOps
        image = ImageOps.exif_transpose(image)
        image.load()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid reference image") from exc

    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def _prepare_diffusion_for_enhancer() -> None:
    pipe = state.pipe
    torch = state.torch
    if pipe is None or torch is None:
        raise RuntimeError("Image runtime is unavailable")

    if state.memory_mode == "gpu":
        pipe.to("cpu")
    else:
        free_hooks = getattr(pipe, "maybe_free_model_hooks", None)
        if callable(free_hooks):
            free_hooks()

    gc.collect()
    torch.cuda.empty_cache()


def _restore_diffusion_after_enhancer() -> None:
    pipe = state.pipe
    if pipe is None:
        raise RuntimeError("Image model is not loaded")
    if state.memory_mode == "gpu":
        pipe.to("cuda")
    else:
        # Reinstall the entire offload sequence after the enhancer. Stale
        # Accelerate hooks can otherwise mix CPU and CUDA on the next request.
        remove = getattr(pipe, "remove_all_hooks", None)
        if callable(remove): remove()
        pipe.to("cpu")
        pipe.enable_model_cpu_offload()


def _enhance_prompt(prompt: str, reference_images: list[Any]) -> PromptEnhancement:
    torch = state.torch
    if torch is None:
        raise RuntimeError("Torch runtime is unavailable")

    _prepare_diffusion_for_enhancer()
    try:
        if reference_images:
            return enhance_i2i(
                prompt,
                reference_images,
                torch=torch,
                model_id=PE_I2I_ID,
            )
        return enhance_t2i(
            prompt,
            torch=torch,
            model_id=PE_T2I_ID,
        )
    finally:
        _restore_diffusion_after_enhancer()


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

    def on_step(_pipe, index, timestep, callback_kwargs):
        phase("generating", MODEL_ID, step=index+1, steps=steps)
        return callback_kwargs
    kwargs["callback_on_step_end"] = on_step
    phase("generating", MODEL_ID, step=0, steps=steps)
    try:
        output = pipe(**kwargs)
        images = getattr(output, "images", None)
        if not images:
            raise RuntimeError("Pipeline returned no image")
        phase("ready", MODEL_ID, step=steps, steps=steps)
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
    enhance_prompt: bool,
) -> dict[str, Any]:
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt cannot be empty")
    _validate_dimensions(width, height)
    _validate_steps(steps)
    if len(reference_images) > MAX_REFERENCE_IMAGES:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_REFERENCE_IMAGES} reference images are supported",
        )

    actual_seed = _normalize_seed(seed)
    effective_prompt = prompt
    prompt_enhanced = False
    enhancer_model: str | None = None
    enhancer_ratio: str | None = None
    enhancer_ratio_follow: str | None = None
    enhancer_fallback = False

    async with generation_lock:
        try:
            await _blocking(_switch_to_image)
        except Exception as exc:
            logger.exception("Image model could not load")
            raise HTTPException(status_code=503, detail="Image model failed to load: " + str(exc)[:300]) from exc
        if enhance_prompt:
            try:
                needed_model = PE_I2I_ID if reference_images else PE_T2I_ID
                if needed_model not in enhancer_ready:
                    _ensure_enhancer_download(needed_model)
                    raise RuntimeError("Requested Qwen enhancer is downloading; this image uses Original")
                enhanced = await _blocking(
                    _enhance_prompt,
                    prompt,
                    reference_images,
                )
                effective_prompt = enhanced.prompt
                prompt_enhanced = True
                enhancer_model = enhanced.model_id
                enhancer_ratio = enhanced.ratio
                enhancer_ratio_follow = enhanced.ratio_follow
                logger.info(
                    "Official Qwen prompt enhancement completed model=%s ratio=%s",
                    enhancer_model,
                    enhancer_ratio,
                )
            except Exception as exc:
                logger.warning("Qwen prompt enhancer unavailable; using original: %s", exc)
                enhancer_fallback = True

        try:
            image = await _blocking(
                _run_pipeline,
                prompt=effective_prompt,
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
            state.pipe = None
            state.active_model = "failed-image"
            _release_gpu()
            phase("failed", MODEL_ID, error="Image inference failed; retry reloads the cached model")
            detail = str(exc)
            if "out of memory" in detail.lower():
                detail = (
                    "GPU ran out of memory. Try Standard quality, fewer/lower-resolution "
                    "reference images, disable prompt enhancement, or use a GPU with more VRAM."
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
        "prompt_enhanced": prompt_enhanced,
        "enhancer_model": enhancer_model,
        "enhancer_ratio": enhancer_ratio,
        "enhancer_ratio_follow": enhancer_ratio_follow,
        "enhancer_fallback": enhancer_fallback,
    }

@app.get("/health")
async def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    return {
        "status": "ok" if state.pipe is not None or state.chat_model is not None else "loading",
        "progress": cache_status(),
        "capabilities": {"chat": state.chat_model is not None, "vision": state.chat_model is not None, "image": state.pipe is not None},
        "model": CHAT_MODEL_ID if state.active_model == "chat" else MODEL_ID,
        "active_model": state.active_model,
        "device": state.device,
        "memory_mode": state.memory_mode,
        "gpu_vram_gb": round(state.gpu_vram_gb, 2),
        "max_reference_images": MAX_REFERENCE_IMAGES,
        "prompt_enhancer": {
            "mode": "on_demand",
            "download_policy": "on_first_enhanced_request",
            "downloading": sorted(enhancer_downloads),
            "cached": sorted(enhancer_ready),
            "t2i_model": PE_T2I_ID,
            "i2i_model": PE_I2I_ID,
            # Enhancement has no fail-closed mode: uncached or failed rewrites
            # always fall back to the original prompt.
            "fail_open": True,
        },
    }


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    if state.pipe is None and state.chat_model is None:
        raise HTTPException(status_code=503, detail="Multimodal model is loading")
    loaded = []
    if state.chat_model is not None: loaded.append(CHAT_MODEL_ID)
    if state.pipe is not None: loaded.append(MODEL_ID)
    return {"object": "list", "data": [{"id": name, "object": "model"} for name in loaded]}



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
        enhance_prompt=request.enhance_prompt,
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
    enhance_prompt: bool = Form(False),
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
        enhance_prompt=enhance_prompt,
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_auth(authorization)
    if len(request.images) > CHAT_MAX_IMAGES:
        raise HTTPException(status_code=422, detail=f"At most {CHAT_MAX_IMAGES} images supported")
    if sum(len(str(turn.get("content", ""))) for turn in request.history) > 16000:
        raise HTTPException(status_code=413, detail="Chat history too long")

    images: list[Any] = []
    for encoded in request.images:
        if len(encoded) > MAX_UPLOAD_BYTES * 4 // 3 + 100:
            raise HTTPException(status_code=413, detail="Image too large")
        try:
            blob = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid base64 image") from exc
        img = _decode_uploaded_image(blob)
        if img.width * img.height > 25_000_000:
            raise HTTPException(status_code=413, detail="Image pixel dimensions too large")
        img.thumbnail((1600, 1600))
        images.append(img.convert("RGB"))

    async with generation_lock:
        try:
            await _blocking(_switch_to_chat)
            reply = await _blocking(
                run_chat,
                state.chat_model,
                state.chat_processor,
                history=request.history,
                prompt=request.prompt,
                images=images,
                max_new_tokens=request.max_new_tokens,
            )
        except Exception as exc:
            logger.exception("Multimodal chat request failed")
            state.chat_model = None
            state.chat_processor = None
            state.active_model = "failed-chat"
            _release_gpu()
            phase("failed", CHAT_MODEL_ID, error="Chat inference failed; retry reloads the cached model")
            raise HTTPException(status_code=500, detail="Chat inference failed: " + str(exc)[:250]) from exc

    return {
        "id": "pixelpilot-chat",
        "object": "chat.completion",
        "model": CHAT_MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
    }
