"""On-demand local Qwen vision/chat runtime.

Images are decoded in the authenticated gateway. The model and processor are
loaded lazily; they never share GPU residency with the diffusion pipeline on
ordinary single-GPU instances.
"""
from __future__ import annotations

import re
from typing import Any


def load_chat_model(model_id: str) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    if not torch.cuda.is_available():
        raise RuntimeError("PixelPilot chat/vision requires a CUDA GPU")
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForMultimodalLM.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    ).eval()
    return model, processor


def run_chat(
    model: Any,
    processor: Any,
    *,
    history: list[dict[str, str]],
    prompt: str,
    images: list[Any],
    max_new_tokens: int,
) -> str:
    """Generate one reply from bounded text history and current visual input."""
    import torch

    messages: list[dict[str, Any]] = []
    for turn in history:
        role = turn.get("role")
        text = turn.get("content")
        if role in {"user", "assistant"} and isinstance(text, str) and text:
            messages.append({"role": role, "content": [{"type": "text", "text": text}]})

    parts: list[dict[str, Any]] = [{"type": "image", "image": img} for img in images]
    parts.append({"type": "text", "text": prompt})
    messages.append({"role": "user", "content": parts})

    encoded = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        enable_thinking=False,
    ).to(model.device)

    with torch.inference_mode():
        tokens = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )
    prompt_tokens = encoded["input_ids"].shape[-1]
    response = processor.decode(
        tokens[0][prompt_tokens:], skip_special_tokens=True
    ).strip()
    # Prevent raw internal thinking markup from reaching Telegram in case a
    # checkpoint ignores enable_thinking=False.
    response = re.sub(r"<think>.*?</think>\s*", "", response, flags=re.DOTALL).strip()
    return response or "لم أتمكن من توليد إجابة. حاول بصياغة أخرى."
