# Architecture

## Controller

Runs permanently on the user's server:
- aiogram Telegram bot and OwnerOnlyMiddleware.
- Rich Message / streamed-draft UI.
- SQLite lifecycle, settings, offer cache and billing metadata.
- RAM-only conversation history.
- Vast SDK gateway and Orchestrator.
- InferenceClient talking to the temporary instance.

## Temporary Vast instance

1. PixelPilot searches for a 48GB+ GPU under the configured price ceiling.
2. Owner confirms rent.
3. Controller generates a random inference bearer token.
4. Vast starts the PyTorch image and runs `scripts/bootstrap_vast.sh`.
5. Bootstrap creates a persistent runtime venv under `/workspace`.
6. It installs vLLM, Qwen VL utilities, OpenAI Whisper, ffmpeg/runtime dependencies.
7. vLLM loads `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8` on localhost port 8191.
8. After vLLM health succeeds, PixelPilot starts the inference gateway on public mapped port 8190.
9. Gateway loads Whisper turbo. In auto mode it uses CUDA only when enough free VRAM remains; otherwise it loads on CPU.
10. Controller probes the gateway's `/health` and `/v1/models` until both vision-language and speech paths are ready.

## Network boundary

```text
Internet / Controller
        |
        | Bearer token
        v
0.0.0.0:8190  PixelPilot inference gateway
        |
        +--> Whisper turbo
        |
        +--> 127.0.0.1:8191 vLLM
                     |
                     +--> Qwen3-VL-30B-A3B-Instruct-FP8
```

vLLM is never bound to the public interface.

## Text / image / video path

Controller sends OpenAI-compatible chat-completion messages to the gateway. The gateway forwards them to vLLM.

- Text stays text.
- Images use `image_url` data URLs.
- Videos use `video_url` data URLs.
- vLLM globally samples 24 video frames and enables frame recovery.
- One image and one video per prompt are allowed by default.

## Voice / audio path

Audio does not go into Qwen3-VL as audio tokens.

1. Controller downloads Telegram Voice/Audio.
2. InferenceClient sends it to `/v1/audio/transcriptions`.
3. Gateway transcribes it with Whisper turbo.
4. Controller replaces the media input with the returned transcript.
5. Transcript + optional Telegram caption are sent to Qwen3-VL.
6. Conversation history stores text transcript only, not audio bytes/base64.

The gateway also understands legacy `audio_url` chat parts and converts them to text as a compatibility fallback.

## Assistant behavior profiles

Neutral mode adds no behavior prompt. If the owner selects a personality/tone/reasoning/format/language/custom prompt, the Controller composes only those visible/editable parts into one typed System text message.

No second hidden Developer/System prompt exists.

Changing a behavior profile clears current RAM history so previous assistant examples cannot anchor the new personality.

## Streaming

vLLM streams SSE chat deltas through the gateway. Controller accumulates them and updates Telegram using `sendMessageDraft` with throttling. On completion it sends one persistent Rich Message; if Rich rendering fails it falls back to plain text.

## Persistence

SQLite stores:
- lifecycle state
- cached offers / refresh serials
- billing meter
- assistant setting selections
- editable prompt profiles
- operational metadata events

Conversation content and media are RAM-only.

## Removed architecture

PixelPilot no longer uses:
- ComfyUI
- FLUX
- image-generation workflows
- Qwen2.5-Omni
- direct public vLLM
