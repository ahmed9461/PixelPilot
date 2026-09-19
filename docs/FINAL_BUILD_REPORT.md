# Final Build Report — v0.6.0

PixelPilot is an owner-only personal multimodal Telegram assistant that rents a temporary Vast.ai GPU only when needed.

## Runtime

```text
Telegram
  -> Controller
  -> authenticated inference gateway
      -> Whisper turbo (Voice/Audio -> transcript)
      -> private vLLM
          -> Qwen3-VL-30B-A3B-Instruct-FP8 (text/image/video)
```

## Quality profile

The Qwen2.5-Omni-7B experiment was retired after live testing showed that its instruction/context following and non-text visual understanding were below the intended personal-assistant quality bar.

v0.6 targets:
- Qwen3-VL 30B-A3B Instruct FP8
- Whisper turbo
- 48GB+ GPU VRAM
- 100GB disk
- 16384-token context
- vLLM GPU utilization 0.82
- hard Vast ceiling $0.50/hour

## Preserved application features

- live Vast marketplace refresh and offer comparison
- per-second billing estimate
- start/stop/destroy and recovery
- Cost Guard
- owner-only access
- RAM-only chat history
- editable behavior profiles/prompts
- Rich Messages and styled Telegram buttons
- streamed AI response drafts
- text/image/video/Voice/audio inputs

## Inference boundary

Only gateway port 8190 is public. vLLM is localhost-only on 8191. The same per-instance random bearer token protects the gateway.

Voice/Audio is transcribed before Qwen chat construction, so follow-up context uses transcript text instead of repeatedly carrying raw audio.

## Validation status

Automated CI validates controller configuration, migrations, inference payloads, speech transcription requests, settings/profile logic, Vast lifecycle and UI regressions.

A real 48GB Vast GPU remains the required live acceptance step for:
- cold-start time
- actual A6000/48GB VRAM headroom
- Whisper CUDA-vs-CPU auto placement
- Arabic conversation quality
- non-text image understanding
- video understanding
- Voice transcription latency
- personality/prompt effect
