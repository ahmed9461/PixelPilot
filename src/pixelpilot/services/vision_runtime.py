"""On-demand local Qwen chat/vision runtime.

The official multimodal checkpoint is the default. An optional community
checkpoint is text-only; neither shares GPU residency with the image
generation/editing pipeline.
"""
from __future__ import annotations

import re
import os
from typing import Any


COMMUNITY_TEXT_MODEL_ID = "lukey03/Qwen3.5-9B-abliterated"


def is_text_only_chat_model(model_id: str) -> bool:
    return model_id == COMMUNITY_TEXT_MODEL_ID


def load_chat_model(model_id: str) -> tuple[Any, Any]:
    import torch
    from pixelpilot.services.model_cache import prepare_model

    if not torch.cuda.is_available():
        raise RuntimeError("PixelPilot chat requires a CUDA GPU")
    local = prepare_model(model_id)
    if is_text_only_chat_model(model_id):
        # The community checkpoint uses qwen3_5_text/Qwen3_5ForCausalLM:
        # loading it with Qwen3_5ForConditionalGeneration is incompatible.
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(local)
        model = AutoModelForCausalLM.from_pretrained(
            local,
            dtype=torch.bfloat16,
            device_map="auto",
            low_cpu_mem_usage=True,
        ).eval()
        return model, tokenizer

    from transformers import Qwen3_5ForConditionalGeneration, AutoProcessor
    processor = AutoProcessor.from_pretrained(local)
    # Prevent the default very large vision-token allocation on 24GB GPUs.
    if getattr(processor, 'image_processor', None) is not None:
        processor.image_processor.size = {'longest_edge': int(os.environ.get('CHAT_IMAGE_MAX_PIXELS', '1048576')), 'shortest_edge': 65536}
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        local,
        dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    ).eval()
    return model, processor


def _strip_fabricated_turns(text: str) -> str:
    """Discard simulated chat roles leaked into a single model response."""
    return re.split(
        r"\r?\n[ \t]*(?:user|assistant)[ \t]*\r?\n",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()


def run_chat(
    model: Any,
    processor: Any,
    *,
    history: list[dict[str, str]],
    prompt: str,
    images: list[Any],
    max_new_tokens: int,
    text_only: bool = False,
) -> str:
    """Generate one reply with the checkpoint's matching chat template."""
    import torch

    if text_only and images:
        raise ValueError("The selected community chat model supports text, not image understanding")

    messages: list[dict[str, Any]] = []
    for turn in history:
        role = turn.get("role")
        text = turn.get("content")
        if role in {"user", "assistant"} and isinstance(text, str) and text:
            content = text if text_only else [{"type": "text", "text": text}]
            messages.append({"role": role, "content": content})

    if text_only:
        messages.append({"role": "user", "content": prompt})
    else:
        parts: list[dict[str, Any]] = [{"type": "image", "image": img} for img in images]
        parts.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": parts})

    budget = int(os.environ.get('CHAT_MAX_INPUT_TOKENS', '8192'))
    while True:
        encoded = processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt", enable_thinking=False,
        )
        if encoded['input_ids'].shape[-1] <= budget:
            break
        if len(messages) <= 1:
            raise ValueError('The message and images exceed the safe context budget; shorten the message or send fewer images')
        # Never truncate image tokens or an interleaved vision sequence.
        messages = messages[2:] if len(messages) > 2 else messages[1:]
    encoded = encoded.to(model.device)

    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
    }
    if text_only:
        # This community checkpoint can continue fabricating user/assistant
        # turns under greedy decoding, burning the full token allowance.
        # Follow Qwen's non-thinking chat sampling recommendations, and stop
        # generation at a real assistant EOS or any fabricated next turn.
        eos_id = getattr(processor, "eos_token_id", None)
        if not isinstance(eos_id, int):
            raise RuntimeError("Community chat tokenizer has no valid EOS token")
        generation_kwargs.update(
            do_sample=True,
            temperature=0.7,
            top_p=0.8,
            top_k=20,
            repetition_penalty=1.1,
            eos_token_id=eos_id,
            pad_token_id=getattr(processor, "pad_token_id", None) or eos_id,
            stop_strings=["<|im_start|>", "\nuser\n", "\nassistant\n"],
            tokenizer=processor,
        )

    with torch.inference_mode():
        tokens = model.generate(
            **encoded,
            **generation_kwargs,
        )
    prompt_tokens = encoded["input_ids"].shape[-1]
    response = processor.decode(
        tokens[0][prompt_tokens:], skip_special_tokens=True
    ).strip()
    if text_only:
        response = _strip_fabricated_turns(response)
    # Prevent raw internal thinking markup from reaching Telegram in case a
    # checkpoint ignores enable_thinking=False.
    response = re.sub(r"<think>.*?</think>\s*", "", response, flags=re.DOTALL).strip()
    if '<think>' in response:
        response = response.partition('<think>')[0].strip()
    return response or "لم أتمكن من توليد إجابة. حاول بصياغة أخرى."
