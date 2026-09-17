# Vast runtime profile

The normal path uses `VAST_DOCKER_IMAGE=vastai/pytorch:@vastai-automatic-tag` plus `scripts/bootstrap_vast.sh`.

Default search policy: one GPU, >= 80 GB VRAM, >= 150 GB disk, verified host, >= 200 Mbps download and one direct mapped port.

The bootstrap installs vLLM and starts `Qwen/Qwen3-Omni-30B-A3B-Instruct` on `INFERENCE_PORT` with a per-instance API key.

A custom `VAST_TEMPLATE_HASH` remains supported if it provides the same runtime contract/environment expected by the controller.
