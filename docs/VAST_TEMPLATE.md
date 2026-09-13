# Vast Deployment Profile

PixelPilot لا يحتاج Template يدويًا إذا استخدمت `PIXELPILOT_REPO_URL`; Controller يستطيع تمرير image/env/onstart مباشرة. Template اختياري لتثبيت defaults.

## Base image

`vastai/pytorch:@vastai-automatic-tag`

## Ports

- `8190/tcp`: Caddy/Portal external app port; Vast يحوله إلى HostPort عشوائي.
- `18190/tcp`: Worker داخلي localhost فقط، لا يفتح عبر Docker.
- `8188/tcp`: ComfyUI localhost فقط.

## Dynamic env injected by Controller

- `HF_TOKEN`
- `PIXELPILOT_WORKER_TOKEN`
- `OPEN_BUTTON_TOKEN` = same per-instance random token
- `OPEN_BUTTON_PORT=8190`
- `PORTAL_CONFIG=localhost:8190:18190:/health:PixelPilot Worker`
- `PIXELPILOT_TRUST_PROXY=1`
- `COMFY_URL=http://127.0.0.1:8188`
- `COMFYUI_REF`
- generation limits
- optional repo URL/ref

`VAST_API_KEY` لا يرسل أبدًا إلى الـGPU instance.

## Direct onstart

إذا `PIXELPILOT_REPO_URL` موجود:

1. clone/fetch `PixelPilot` إلى `/workspace/PixelPilot`.
2. تشغيل `scripts/bootstrap_vast.sh` في الخلفية.
3. bootstrap ينزل ComfyUI + dependencies + models.
4. يبدأ ComfyUI.
5. بعد readiness يبدأ Worker.

## Template identifier

إذا استخدمت Vast Template، ضع `hash_id` في `VAST_TEMPLATE_HASH`. لا تستخدم numeric `id` عند Create Instance.
