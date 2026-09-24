# Architecture

## Controller

The persistent PixelPilot controller runs:
- aiogram Telegram polling
- owner-only middleware
- SQLite state/settings/events
- Vast marketplace and instance lifecycle
- billing/cost guard
- authenticated calls to the temporary image worker

The controller does not load the image model locally.

## Temporary GPU worker

Each Vast instance runs:
- CUDA-enabled PyTorch from the Vast image
- Transformers + Accelerate
- current Diffusers with `QwenImage21Pipeline`
- FastAPI/Uvicorn image gateway on port 8190

The worker supports:
- `GET /health`
- `GET /v1/models`
- `POST /v1/images/generations`
- `POST /v1/images/edits`

Every endpoint requires the random bearer token generated when the instance is rented.

## Memory policy

`IMAGE_MEMORY_MODE=auto`:
- rounded VRAM >= 48 GB: full GPU
- otherwise: Diffusers model CPU offload

VAE tiling and slicing remain enabled by default.

Vast discovery accepts 24 GB+ GPUs but ranks 48 GB+ offers ahead of lower-memory fallback offers.

## Prompt path

```text
Telegram text/caption
  -> non-empty validation
  -> InferenceClient
  -> image gateway
  -> QwenImage21Pipeline
```

There is no chat history, persona layer or tone layer. Prompt rewriting occurs only when the owner explicitly selects the official Qwen Prompt Enhancer; Original mode sends the prompt unchanged.

## Reference images

- one Telegram photo/document can be used as an edit reference
- Telegram photo albums are collected in memory and sent together
- maximum references: 10
- image bytes are not persisted in SQLite

## Output

The gateway encodes the generated PIL image as PNG base64 for transport to the controller. The controller decodes it and sends a PNG document to Telegram with output size and seed.
