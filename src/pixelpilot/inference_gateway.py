from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

logger = logging.getLogger("pixelpilot.inference_gateway")

TOKEN = os.environ.get("PIXELPILOT_INFERENCE_TOKEN", "")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8")
VLLM_INTERNAL_PORT = int(os.environ.get("VLLM_INTERNAL_PORT", "8191"))
VLLM_URL = os.environ.get("VLLM_URL", f"http://127.0.0.1:{VLLM_INTERNAL_PORT}").rstrip("/")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "turbo")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto").strip().lower()
WHISPER_CACHE = os.environ.get("WHISPER_CACHE", "/workspace/whisper-cache")
WHISPER_MIN_FREE_VRAM_GB = float(os.environ.get("WHISPER_MIN_FREE_VRAM_GB", "6"))
MAX_AUDIO_BYTES = int(os.environ.get("MAX_AUDIO_BYTES", str(32 * 1024 * 1024)))


class RuntimeState:
    whisper: Any | None = None
    whisper_device: str = "unknown"
    whisper_lock: asyncio.Lock


state = RuntimeState()
state.whisper_lock = asyncio.Lock()


def _authorized(value: str | None) -> bool:
    return bool(TOKEN) and value == f"Bearer {TOKEN}"


def _check_auth(value: str | None) -> None:
    if not _authorized(value):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _upstream_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


async def _wait_for_vllm() -> None:
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            try:
                response = await client.get(
                    f"{VLLM_URL}/health",
                    headers={"Authorization": f"Bearer {TOKEN}"},
                )
                if response.is_success:
                    return
            except Exception:
                pass
            await asyncio.sleep(2.0)


def _choose_whisper_device() -> str:
    if WHISPER_DEVICE in {"cuda", "cpu"}:
        return WHISPER_DEVICE

    try:
        import torch

        if not torch.cuda.is_available():
            return "cpu"
        free_bytes, _total_bytes = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024**3)
        if free_gb >= WHISPER_MIN_FREE_VRAM_GB:
            return "cuda"
    except Exception:
        logger.exception("Could not inspect CUDA memory for Whisper auto-selection")
    return "cpu"


def _load_whisper() -> tuple[Any, str]:
    import whisper

    Path(WHISPER_CACHE).mkdir(parents=True, exist_ok=True)
    device = _choose_whisper_device()
    logger.info("Loading Whisper model=%s device=%s", WHISPER_MODEL, device)
    try:
        model = whisper.load_model(
            WHISPER_MODEL,
            device=device,
            download_root=WHISPER_CACHE,
        )
        return model, device
    except Exception:
        if WHISPER_DEVICE == "auto" and device == "cuda":
            logger.exception("Whisper CUDA load failed; retrying on CPU")
            model = whisper.load_model(
                WHISPER_MODEL,
                device="cpu",
                download_root=WHISPER_CACHE,
            )
            return model, "cpu"
        raise


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not TOKEN:
        raise RuntimeError("PIXELPILOT_INFERENCE_TOKEN is required")

    logger.info("Waiting for internal vLLM endpoint at %s", VLLM_URL)
    await _wait_for_vllm()
    state.whisper, state.whisper_device = await asyncio.to_thread(_load_whisper)
    logger.info(
        "PixelPilot gateway ready: model=%s whisper=%s/%s",
        MODEL_ID,
        WHISPER_MODEL,
        state.whisper_device,
    )
    yield
    state.whisper = None


app = FastAPI(title="PixelPilot Inference Gateway", lifespan=lifespan)


def _suffix_for_mime(mime_type: str) -> str:
    value = mime_type.lower()
    if "ogg" in value:
        return ".ogg"
    if "wav" in value:
        return ".wav"
    if "mp4" in value or "m4a" in value:
        return ".m4a"
    if "webm" in value:
        return ".webm"
    if "mpeg" in value or "mp3" in value:
        return ".mp3"
    return ".audio"


async def _transcribe_bytes(data: bytes, mime_type: str) -> str:
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large")
    if state.whisper is None:
        raise HTTPException(status_code=503, detail="Speech model is not ready")

    suffix = _suffix_for_mime(mime_type)
    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(data)
            path = handle.name

        async with state.whisper_lock:
            result = await asyncio.to_thread(
                state.whisper.transcribe,
                path,
                fp16=state.whisper_device == "cuda",
                temperature=0.0,
                condition_on_previous_text=False,
            )
        text = str(result.get("text") or "").strip() if isinstance(result, dict) else ""
        if not text:
            raise HTTPException(status_code=422, detail="No speech could be transcribed")
        return text
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _decode_audio_data_url(url: str) -> tuple[bytes, str]:
    if not url.startswith("data:") or ";base64," not in url:
        raise HTTPException(status_code=400, detail="Only base64 audio data URLs are supported")
    header, encoded = url.split(",", 1)
    mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    try:
        return base64.b64decode(encoded, validate=True), mime_type
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 audio payload") from exc


async def _replace_audio_parts(messages: Any) -> Any:
    """Compatibility path for older controllers that still send audio_url."""
    if not isinstance(messages, list):
        return messages

    rewritten: list[Any] = []
    for message in messages:
        if not isinstance(message, dict):
            rewritten.append(message)
            continue
        content = message.get("content")
        if not isinstance(content, list):
            rewritten.append(message)
            continue

        new_parts: list[Any] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "audio_url":
                new_parts.append(part)
                continue
            audio = part.get("audio_url")
            url = audio.get("url") if isinstance(audio, dict) else None
            if not isinstance(url, str):
                raise HTTPException(status_code=400, detail="Invalid audio_url payload")
            data, mime_type = _decode_audio_data_url(url)
            transcript = await _transcribe_bytes(data, mime_type)
            new_parts.append({"type": "text", "text": transcript})

        updated = dict(message)
        updated["content"] = new_parts
        rewritten.append(updated)
    return rewritten


@app.get("/health")
async def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    if state.whisper is None:
        raise HTTPException(status_code=503, detail="Speech model is loading")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{VLLM_URL}/health",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Vision-language model is not ready") from exc
    return {
        "status": "ok",
        "model": MODEL_ID,
        "speech_model": WHISPER_MODEL,
        "speech_device": state.whisper_device,
    }


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> Response:
    _check_auth(authorization)
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{VLLM_URL}/v1/models",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form(default="turbo"),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _check_auth(authorization)
    del model  # The gateway serves the configured Whisper model only.
    data = await file.read()
    text = await _transcribe_bytes(data, file.content_type or "application/octet-stream")
    return {"text": text}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _check_auth(authorization)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid chat payload")

    if "messages" in payload:
        payload["messages"] = await _replace_audio_parts(payload["messages"])

    stream = bool(payload.get("stream"))
    client = httpx.AsyncClient(timeout=None, follow_redirects=True)
    upstream_request = client.build_request(
        "POST",
        f"{VLLM_URL}/v1/chat/completions",
        headers=_upstream_headers(),
        json=payload,
    )
    upstream = await client.send(upstream_request, stream=stream)

    if not stream:
        try:
            body = await upstream.aread()
            return Response(
                content=body,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "application/json"),
            )
        finally:
            await upstream.aclose()
            await client.aclose()

    if upstream.is_error:
        try:
            body = await upstream.aread()
            return JSONResponse(
                status_code=upstream.status_code,
                content={
                    "error": {
                        "message": body.decode("utf-8", errors="replace")[:2000],
                        "type": "UpstreamError",
                    }
                },
            )
        finally:
            await upstream.aclose()
            await client.aclose()

    async def stream_body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "text/event-stream"),
    )
