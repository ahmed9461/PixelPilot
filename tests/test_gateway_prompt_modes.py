import asyncio
import io

from pixelpilot import inference_gateway as gateway
from pixelpilot.services.prompt_enhancer import PromptEnhancement


class FakeImage:
    def save(self, buffer: io.BytesIO, *, format: str):
        assert format == "PNG"
        buffer.write(b"PNG")


def test_original_preserves_prompt_and_enhancer_failure_falls_back(monkeypatch):
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["prompt"])
        return FakeImage()

    def broken_enhancer(prompt, images):
        raise RuntimeError("model failed")

    monkeypatch.setattr(gateway, "_run_pipeline", generate)
    monkeypatch.setattr(gateway, "_enhance_prompt", broken_enhancer)
    gateway.enhancer_ready.add(gateway.PE_T2I_ID)

    async def scenario():
        base = dict(prompt="  my exact prompt  ", width=1024, height=1024,
                    steps=20, seed=123, reference_images=[], true_cfg_scale=1.0,
                    negative_prompt=None)
        original = await gateway._generate_response(**base, enhance_prompt=False)
        fallback = await gateway._generate_response(**base, enhance_prompt=True)
        assert prompts == [base["prompt"], base["prompt"]]
        assert original["prompt_enhanced"] is False
        assert original["enhancer_fallback"] is False
        assert fallback["enhancer_fallback"] is True

    try:
        asyncio.run(scenario())
    finally:
        gateway.enhancer_ready.discard(gateway.PE_T2I_ID)


def test_optional_enhancer_uses_official_result_when_cached(monkeypatch):
    prompts = []
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs: (prompts.append(kwargs["prompt"]), FakeImage())[1])
    monkeypatch.setattr(gateway, "_enhance_prompt", lambda prompt, images:
                        PromptEnhancement("enhanced", gateway.PE_T2I_ID))
    gateway.enhancer_ready.add(gateway.PE_T2I_ID)

    async def scenario():
        result = await gateway._generate_response(
            prompt="original", width=1024, height=1024, steps=20, seed=123,
            reference_images=[], true_cfg_scale=1.0, negative_prompt=None,
            enhance_prompt=True,
        )
        assert prompts == ["enhanced"]
        assert result["prompt_enhanced"] is True
        assert result["enhancer_fallback"] is False

    try:
        asyncio.run(scenario())
    finally:
        gateway.enhancer_ready.discard(gateway.PE_T2I_ID)


def test_uncached_enhancer_falls_back_without_starting_model_load(monkeypatch):
    prompts = []
    gateway.enhancer_ready.discard(gateway.PE_T2I_ID)
    monkeypatch.setattr(gateway, "_enhance_prompt", lambda *args: (_ for _ in ()).throw(
        AssertionError("uncached enhancer must not load during an image request")))
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs:
                        (prompts.append(kwargs["prompt"]), FakeImage())[1])

    async def scenario():
        result = await gateway._generate_response(
            prompt="  unchanged  ", width=1024, height=1024, steps=20, seed=123,
            reference_images=[], true_cfg_scale=1.0, negative_prompt=None,
            enhance_prompt=True,
        )
        assert prompts == ["  unchanged  "]
        assert result["enhancer_fallback"] is True

    asyncio.run(scenario())
