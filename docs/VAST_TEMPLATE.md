# Vast.ai Template Notes

Use a CUDA-enabled Vast PyTorch image and expose one direct TCP port for the PixelPilot image gateway.

Recommended controller defaults:
- image: `vastai/pytorch:@vastai-automatic-tag`
- disk: 100 GB
- minimum VRAM: 24 GB
- preferred VRAM: 48 GB+
- minimum host RAM: 48 GB
- direct ports: at least 1
- download bandwidth: at least 100 Mbps
- reliability: at least 0.98

The controller passes runtime variables and an on-start command. The on-start flow clones PixelPilot and launches `scripts/bootstrap_vast.sh`.

Do not preconfigure vLLM or Whisper in the template. Qwen-Image-2.1 is loaded directly through Diffusers.
