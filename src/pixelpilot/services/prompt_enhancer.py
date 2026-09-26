from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


T2I_MAX_NEW_TOKENS = 16256
EDIT_MAX_NEW_TOKENS = 24000
IMAGE_MAX_PIXELS = 1024 * 1024
TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 20
T2I_PRESENCE_PENALTY = 1.5
EDIT_PRESENCE_PENALTY = 0.0
DEFAULT_SEED = 42


@dataclass(slots=True, frozen=True)
class PromptEnhancement:
    prompt: str
    model_id: str
    ratio: str | None = None
    ratio_follow: str | None = None


def _balanced_json_objects(text: str) -> list[str]:
    spans: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                spans.append(text[start : index + 1])
    return spans


def _answer_section(generated: str) -> str:
    if "</think>" in generated:
        return generated.partition("</think>")[2].strip()
    if "<think>" in generated:
        return ""
    return generated.strip()


def parse_enhancer_output(
    generated: str,
    *,
    include_ratio_follow: bool = False,
) -> tuple[str, str | None, str | None]:
    answer = _answer_section(generated)
    if not answer:
        raise RuntimeError("Prompt enhancer returned no answer after thinking")

    for candidate in reversed(_balanced_json_objects(answer)):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        rewritten = payload.get("rewritten_prompt") or payload.get("rewrited_prompt")
        if not isinstance(rewritten, str) or not rewritten.strip():
            continue

        ratio_value = payload.get("wh_ratio")
        ratio = str(ratio_value).strip() if isinstance(ratio_value, str) and ratio_value.strip() else None
        ratio_follow: str | None = None
        if include_ratio_follow:
            follow_value = payload.get("ratio_follow")
            if isinstance(follow_value, str) and follow_value.strip():
                ratio_follow = follow_value.strip()

        return rewritten.strip(), ratio, ratio_follow

    raise RuntimeError("Prompt enhancer returned no valid rewritten_prompt JSON object")


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


def _resize_reference(image: Any) -> Any:
    from PIL import Image

    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = width * height
    if pixels <= IMAGE_MAX_PIXELS:
        return rgb

    scale = (IMAGE_MAX_PIXELS / float(pixels)) ** 0.5
    target = (max(1, int(width * scale)), max(1, int(height * scale)))
    return rgb.resize(target, Image.Resampling.LANCZOS)


def _build_messages(system_prompt: str, prompt: str, images: list[Any]) -> list[dict[str, Any]]:
    user_content: list[dict[str, Any]] = [
        {"type": "image", "image": image}
        for image in images
    ]
    user_content.append({"type": "text", "text": prompt})
    return [
        {
            "role": "system",
            "content": [{"type": "text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]


def _presence_penalty_processor(
    *,
    penalty: float,
    prompt_len: int,
) -> Any:
    from transformers import LogitsProcessor

    class PresencePenalty(LogitsProcessor):
        def __call__(self, input_ids: Any, scores: Any) -> Any:
            for batch_index in range(input_ids.shape[0]):
                generated = input_ids[batch_index, prompt_len:]
                if generated.numel():
                    scores[batch_index, generated.unique()] -= penalty
            return scores

    return PresencePenalty()


def _enhance(
    prompt: str,
    images: list[Any],
    *,
    torch: Any,
    model_id: str,
    max_new_tokens: int,
    presence_penalty: float,
    include_ratio_follow: bool,
) -> PromptEnhancement:
    from transformers import AutoModelForImageTextToText, AutoProcessor, LogitsProcessorList

    processor = None
    model = None
    inputs = None
    output = None
    try:
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        ).to("cuda").eval()

        messages = _build_messages(
            _system_prompt(model_id),
            prompt,
            images,
        )
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            enable_thinking=True,
        ).to(model.device)

        if (
            "mm_token_type_ids" not in inputs
            and hasattr(processor, "create_mm_token_type_ids")
        ):
            inputs["mm_token_type_ids"] = processor.create_mm_token_type_ids(
                inputs["input_ids"]
            )

        prompt_len = inputs["input_ids"].shape[1]
        logits_processors = LogitsProcessorList()
        if presence_penalty:
            logits_processors.append(
                _presence_penalty_processor(
                    penalty=presence_penalty,
                    prompt_len=prompt_len,
                )
            )

        torch.manual_seed(DEFAULT_SEED)
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                top_k=TOP_K,
                logits_processor=logits_processors,
                pad_token_id=processor.tokenizer.eos_token_id,
            )

        generated = processor.tokenizer.decode(
            output[0, prompt_len:],
            skip_special_tokens=True,
        )
        rewritten, ratio, ratio_follow = parse_enhancer_output(
            generated,
            include_ratio_follow=include_ratio_follow,
        )
        return PromptEnhancement(
            prompt=rewritten,
            model_id=model_id,
            ratio=ratio,
            ratio_follow=ratio_follow,
        )
    finally:
        output = None
        inputs = None
        model = None
        processor = None
        _cleanup(torch)


def enhance_t2i(
    prompt: str,
    *,
    torch: Any,
    model_id: str,
) -> PromptEnhancement:
    return _enhance(
        prompt,
        [],
        torch=torch,
        model_id=model_id,
        max_new_tokens=T2I_MAX_NEW_TOKENS,
        presence_penalty=T2I_PRESENCE_PENALTY,
        include_ratio_follow=False,
    )


def enhance_i2i(
    prompt: str,
    images: list[Any],
    *,
    torch: Any,
    model_id: str,
) -> PromptEnhancement:
    if not images:
        raise RuntimeError("I2I prompt enhancer requires at least one reference image")

    resized = [_resize_reference(image) for image in images]
    return _enhance(
        prompt,
        resized,
        torch=torch,
        model_id=model_id,
        max_new_tokens=EDIT_MAX_NEW_TOKENS,
        presence_penalty=EDIT_PRESENCE_PENALTY,
        include_ratio_follow=True,
    )
