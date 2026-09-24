# PixelPilot

PixelPilot is an owner-only Telegram image studio that rents a temporary Vast.ai GPU and runs **Qwen/Qwen-Image-2.1** for image generation and image editing.

## What it does

- Text → image generation.
- Image + instruction → image editing.
- Telegram albums can provide up to 10 reference images.
- Output is delivered as PNG to preserve full quality and alpha/transparency when produced.
- Image settings: aspect ratio, Standard/2K quality, and inference steps.
- Vast lifecycle: live offer search, rent, provision, stop, start, destroy, cost meter, recovery and preflight.
- Owner-only Telegram access.

PixelPilot does **not** inject a hidden system/developer prompt, personality, emotion, tone or chat history. The owner chooses between **Original Prompt** (sent unchanged) and the official **Qwen Prompt Enhancer** for Qwen-Image-2.1.

## Runtime

Controller:

```text
Telegram
  -> PixelPilot controller
     -> SQLite lifecycle/settings/billing
     -> authenticated temporary Vast endpoint :8190
        -> QwenImage21Pipeline
```

The GPU instance loads the Diffusers `QwenImage21Pipeline` directly. vLLM, Qwen3-VL and Whisper are not part of the image runtime.

## GPU / VRAM policy

The BF16 Qwen-Image-2.1 checkpoint is roughly 33 GB before runtime overhead.

- **24 GB VRAM**: supported through model CPU offload + VAE tiling/slicing when the host has at least **64 GB system RAM**. Best with Standard resolution; edits with many references can be slower and may need lower memory pressure.
- **48 GB+ VRAM**: preferred. PixelPilot keeps the pipeline on GPU in `auto` mode for better speed and 2K work.
- Vast search minimum: **24 GB**.
- Preferred offer tier: **48 GB+**.
- Minimum host RAM for the supported image + prompt-enhancer profile: **64 GB**.
- Default disk: **100 GB**.
- Hard rental ceiling: **$0.50/hour**.

The offer list keeps 24 GB fallback machines available while ranking suitable 48 GB+ machines first.

## Image presets

Standard presets are designed for lower VRAM and faster iteration:

| Ratio | Size |
|---|---:|
| 1:1 | 1024×1024 |
| 4:3 | 1152×896 |
| 3:4 | 896×1152 |
| 3:2 | 1216×832 |
| 2:3 | 832×1216 |
| 16:9 | 1344×768 |
| 9:16 | 768×1344 |

2K mode uses the Qwen-Image-2.1 model-card aspect-ratio sizes, including 2048×2048 for 1:1 and 2752×1536 for 16:9.

Default inference steps: **40**.

## First-run configuration

Copy `.env.example` to `.env` or run:

```bash
python scripts/configure_secrets.py
python scripts/preflight.py
```

Required controller values:

- `TELEGRAM_BOT_TOKEN`
- `OWNER_TELEGRAM_ID`
- `VAST_API_KEY`
- `PIXELPILOT_REPO_URL` or `VAST_TEMPLATE_HASH`

`HF_TOKEN` is optional because the model is public.

## Vast bootstrap

A rented instance clones the configured repository/ref and runs:

```bash
scripts/bootstrap_vast.sh
```

The bootstrap:

1. reuses the Vast CUDA-enabled PyTorch environment,
2. installs current Transformers, Accelerate, Pillow and the Diffusers version required for Qwen-Image-2.1,
3. loads `QwenImage21Pipeline`,
4. chooses full-GPU vs CPU-offload mode automatically,
5. enables VAE tiling/slicing,
6. exposes one authenticated FastAPI image endpoint.

## Telegram usage

- Send text to generate an image.
- Send one image with a caption to edit it.
- Send an album of up to 10 images with an instruction in the album caption to use multiple references.
- Open **⚙️ إعدادات الصور** to choose quality, aspect ratio and steps.

There is no conversation memory because the product is an image studio rather than a chat assistant.

## Security

- Vast API credentials stay on the controller.
- Every temporary image endpoint gets a random bearer token.
- The model endpoint is not exposed without authentication.
- Generated image bytes are returned to Telegram and are not persisted by PixelPilot.
- Rental deletion remains owner-controlled unless explicitly configured otherwise.

## Model license

Qwen-Image-2.1 is distributed under the **Qwen Research License**. Review the upstream license before any non-personal/commercial deployment.

Official model card:
https://huggingface.co/Qwen/Qwen-Image-2.1
