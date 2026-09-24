from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class PromptEnhancement:
    prompt: str
    model_id: str
    ratio: str | None = None


def parse_enhancer_output(generated: str) -> tuple[str, str | None]:
    _thinking, separator, answer = generated.partition("</think>")
    candidate = (answer if separator else generated).strip()

    if candidate.startswith("```"):
        parts = candidate.split("```")
        if len(parts) >= 3:
            candidate = parts[1].strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].lstrip()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Prompt enhancer returned no JSON object")
        payload = json.loads(candidate[start : end + 1])

    if not isinstance(payload, dict):
        raise RuntimeError("Prompt enhancer returned an invalid JSON payload")
    rewritten = payload.get("rewritten_prompt")
    if not isinstance(rewritten, str) or not rewritten.strip():
        raise RuntimeError("Prompt enhancer returned no rewritten_prompt")

    ratio = payload.get("wh_ratio")
    normalized_ratio = str(ratio) if isinstance(ratio, str) and ratio else None
    return rewritten, normalized_ratio


def _system_prompt(model_id: str) -> str:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(model_id, "system_prompt.txt")
    return Path(path).read_text(encoding="utf-8").strip()


def _cleanup(torch: Any) -> None:
    gc.collect()
    try:
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    except Exception:
        pass


def enhance_t2i(
    prompt: str,
    *,
    torch: Any,
    model_id: str,
    max_new_tokens: int,
) -> PromptEnhancement:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = None
    model = None
    inputs = None
    output = None
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
        ).eval()
        text = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": _system_prompt(model_id)},
                {"role": "user", "content": prompt},
            ],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        inputs = tokenizer(text, return_tensors="pt").to("cuda")
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=1.0,
                top_p=0.95,
                top_k=20,
            )
        generated = tokenizer.decode(
            output[0, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
        )
        rewritten, ratio = parse_enhancer_output(generated)
        return PromptEnhancement(prompt=rewritten, model_id=model_id, ratio=ratio)
    finally:
        output = None
        inputs = None
        model = None
        tokenizer = None
        _cleanup(torch)


def enhance_i2i(
    prompt: str,
    images: list[Any],
    *,
    torch: Any,
    model_id: str,
    max_new_tokens: int,
) -> PromptEnhancement:
    from transformers import AutoModelForImageTextToText, AutoProcessor

    if not images:
        raise RuntimeError("I2I prompt enhancer requires at least one reference image")

    processor = None
    model = None
    inputs = None
    output = None
    try:
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            device_map={"": 0},
            low_cpu_mem_usage=True,
        ).eval()
        user_content: list[dict[str, Any]] = [
            {"type": "image", "image": image.convert("RGB")}
            for image in images
        ]
        user_content.append({"type": "text", "text": prompt})
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": _system_prompt(model_id)}],
            },
            {"role": "user", "content": user_content},
        ]
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            enable_thinking=True,
        ).to("cuda")
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=1.0,
                top_p=0.95,
                top_k=20,
            )
        generated = processor.tokenizer.decode(
            output[0, inputs["input_ids"].shape[1] :],
            skip_special_tokens=True,
        )
        rewritten, ratio = parse_enhancer_output(generated)
        return PromptEnhancement(prompt=rewritten, model_id=model_id, ratio=ratio)
    finally:
        output = None
        inputs = None
        model = None
        processor = None
        _cleanup(torch)