# Vast runtime profile

The normal path uses `VAST_DOCKER_IMAGE=vastai/pytorch:@vastai-automatic-tag` plus `scripts/bootstrap_vast.sh`.

Default economy search policy: one GPU, >= 48 GB VRAM, >= 80 GB disk, verified host, >= 100 Mbps download and one direct mapped port. The default hard price cap is `$0.80/hour`.

The bootstrap installs vLLM and starts `Qwen/Qwen2.5-Omni-7B` on `INFERENCE_PORT` with a per-instance API key. The default context is 8192 tokens to preserve headroom on 48GB-class GPUs.

A custom `VAST_TEMPLATE_HASH` remains supported if it provides the same runtime contract/environment expected by the controller.
