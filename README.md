# PixelPilot

PixelPilot is an owner-only Telegram image studio that rents a temporary Vast.ai GPU and runs **Qwen/Qwen-Image-2.1** for image generation and image editing.

## What it does

- Text → image generation.
- Image + instruction → image editing, including Telegram albums with up to 10 references.
- PNG output preserving full quality and alpha/transparency when produced.
- Aspect ratio, Standard/2K quality, inference-step and explicit prompt-mode controls.
- Live Vast offer search, transfer-aware cost comparison, rent/provision/stop/start/destroy, running-time estimate, recovery and preflight.
- Owner-only Telegram access.

PixelPilot does **not** inject a hidden personality, emotion, tone or chat history. The owner chooses **Original Prompt** (sent unchanged) or the official **Qwen Prompt Enhancer**, which uses its checkpoint's official rewrite instructions.

## Runtime

```text
Telegram
  -> PixelPilot controller
     -> SQLite lifecycle/settings/running-time estimate
     -> authenticated temporary Vast endpoint :8190
        -> QwenImage21Pipeline
```

The GPU instance loads the Diffusers `QwenImage21Pipeline` directly. vLLM, Qwen3-VL and Whisper are not part of the image runtime.

## GPU / VRAM policy

The BF16 Qwen-Image-2.1 checkpoint is roughly 33 GB before runtime overhead.

- **24 GB VRAM**: CPU offload + VAE tiling/slicing, with a **48 GB host RAM** search floor. Start with Standard resolution; large edits or enhancement may need more RAM.
- **48 GB+ VRAM**: preferred execution tier; the pipeline stays on GPU in `auto` mode for better speed and 2K work. Full-GPU offers have no unconditional host-RAM filter.
- Default disk: **100 GB**. Hard hourly rental ceiling: **$0.50/hour**, not an all-in spending limit.

Discovery scans a wider live pool than the 8 rows shown in Telegram. Normal search queries 48 GB+ and 24 GB+ fallback candidates, deduplicates them and compares their download-inclusive estimated cost. Known quotes rank before unknown rates; hardware preference breaks equal-cost ties. A separate `48GB+ only` view remains available.

Before rent, PixelPilot re-reads the machine from the discovery snapshot and accepts only the exact original Offer ID. This works around Vast's observed `/bundles/` `id` lookup mismatch without substituting another ask. Changes in GPU/VRAM, hourly price, Download or Upload quotes require refreshed confirmation. A timeout or server error retains a pending label and blocks another rent until reconciliation. `cancel_unavail=true` remains required.

## Transfer-aware selection

The offer list displays **Download $/TB**, and details show both transfer directions before confirmation. Native `inet_down_cost` / `inet_up_cost` are precise USD/GB rates; the explicit display convention is **1 TB = 1000 GB**. Unknown, invalid or missing rates are not treated as free.

```text
Comparison estimate = billed hours × hourly dph_total
                    + assumed download GB × inbound USD/GB
```

Defaults are configurable:

```dotenv
VAST_ESTIMATED_DOWNLOAD_GB=70
VAST_COST_COMPARISON_HOURS=1
# Optional, owner-selected inbound rate ceiling; absent by default:
# VAST_MAX_DOWNLOAD_USD_PER_TB=5
```

70 GB is a comparison allowance, not a measured model filesize or download promise. Billed time includes setup; actual time may exceed the comparison period. Allocated storage is already included in `dph_total` and is not added twice. Upload, optional enhancer downloads, extra transfers/retries and storage while stopped can add costs. The running-time meter is **not the total or final Vast invoice**.

A configured Download ceiling is checked in discovery, local filtering and again before creation; unknown rates are excluded when that ceiling is enabled. Zero accepts genuinely free inbound quotes only. No arbitrary additional rate ceiling is imposed by default, and a rate ceiling does not guarantee a final spending total.

## Image presets

Standard presets:

| Ratio | Size |
|---|---:|
| 1:1 | 1024×1024 |
| 4:3 | 1152×896 |
| 3:4 | 896×1152 |
| 3:2 | 1216×832 |
| 2:3 | 832×1216 |
| 16:9 | 1344×768 |
| 9:16 | 768×1344 |

2K uses the model-card aspect-ratio sizes, including 2048×2048 for 1:1 and 2752×1536 for 16:9. Default steps: **40**.

## Configuration and deployment

For a new installation, copy `.env.example` to `.env` or use:

```bash
python scripts/configure_secrets.py
python scripts/preflight.py
```

Required controller values: `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_ID`, `VAST_API_KEY`, and `PIXELPILOT_REPO_URL` or `VAST_TEMPLATE_HASH`. `HF_TOKEN` is optional.

For an existing installation, preserve its `.env` and SQLite. Follow [the runbook](docs/RUNBOOK.md) and deploy from the stable `main` baseline. Keep the controller checkout and worker `PIXELPILOT_REPO_REF` aligned to `main`; a repository push does not update an existing VPS or worker automatically. See [the completed cost-awareness plan](docs/DOWNLOAD_COST_PLAN.md) for the implementation and validation history.

## Vast bootstrap

A rented instance clones the configured repository/ref and runs `scripts/bootstrap_vast.sh`. It reuses the CUDA-enabled PyTorch environment, installs the required Transformers/Accelerate/Pillow/Diffusers dependencies, loads `QwenImage21Pipeline`, selects full-GPU or CPU offload, enables VAE tiling/slicing, and exposes an authenticated FastAPI image endpoint.

## Telegram usage

- Send text to generate an image, one image with a caption to edit, or an album of up to 10 references with instructions in its caption.
- Open **⚙️ إعدادات الصور** to select quality, aspect ratio, steps and prompt mode.
- **Original** is the default and starts no optional enhancer downloads. The first explicit **Qwen Enhance** request starts only the needed T2I or I2I checkpoint download. Until cached, or on enhancement failure, that image uses the original prompt and reports fallback. Subsequent requests can use the cached enhancer. Optional checkpoint downloads may add transfer charges.

There is no conversation memory; each image request is independent.

## Security

Vast credentials stay on the controller. Each temporary image endpoint has a random bearer token and requires authentication. Generated/reference images are not persisted in SQLite. Automatic deletion is opt-in; trial cleanup must never delete unrelated existing instances.

## Model license

Qwen-Image-2.1 is distributed under the **Qwen Research License**. Review the upstream license before non-personal/commercial deployment.

Official model card: https://huggingface.co/Qwen/Qwen-Image-2.1
