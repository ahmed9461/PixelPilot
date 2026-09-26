import asyncio
import io
import sys
from types import SimpleNamespace

import pytest

from pixelpilot import inference_gateway as gateway
from pixelpilot.services.prompt_enhancer import PromptEnhancement


class FakeImage:
    def save(self, buffer: io.BytesIO, *, format: str):
        assert format == "PNG"
        buffer.write(b"PNG")


@pytest.fixture(autouse=True)
def isolated_enhancer_state(monkeypatch):
    monkeypatch.setattr(gateway, "enhancer_ready", set())
    monkeypatch.setattr(gateway, "enhancer_downloads", {})


def request_kwargs(*, editing=False):
    return dict(prompt="  my exact prompt  ", width=1024, height=1024,
                steps=20, seed=123, reference_images=[object()] if editing else [],
                true_cfg_scale=1.0, negative_prompt=None)


def test_health_reports_fixed_fail_open_policy(monkeypatch):
    monkeypatch.setattr(gateway, "TOKEN", "test-token")
    monkeypatch.setattr(gateway.state, "pipe", object())
    result = asyncio.run(gateway.health("Bearer test-token"))
    assert result["status"] == "ok"
    assert result["prompt_enhancer"]["fail_open"] is True
    assert result["prompt_enhancer"]["download_policy"] == "on_first_enhanced_request"


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
        base = request_kwargs()
        original = await gateway._generate_response(**base, enhance_prompt=False)
        fallback = await gateway._generate_response(**base, enhance_prompt=True)
        assert prompts == [base["prompt"], base["prompt"]]
        assert original["prompt_enhanced"] is False
        assert original["enhancer_fallback"] is False
        assert fallback["enhancer_fallback"] is True

    asyncio.run(scenario())


def test_optional_enhancer_uses_official_result_when_cached(monkeypatch):
    prompts = []
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs: (prompts.append(kwargs["prompt"]), FakeImage())[1])
    monkeypatch.setattr(gateway, "_enhance_prompt", lambda prompt, images:
                        PromptEnhancement("enhanced", gateway.PE_T2I_ID))
    gateway.enhancer_ready.add(gateway.PE_T2I_ID)

    async def scenario():
        result = await gateway._generate_response(**request_kwargs(), enhance_prompt=True)
        assert prompts == ["enhanced"]
        assert result["prompt_enhanced"] is True
        assert result["enhancer_fallback"] is False

    asyncio.run(scenario())


def test_uncached_enhancer_falls_back_without_starting_model_load(monkeypatch):
    prompts = []
    downloads = []
    monkeypatch.setattr(gateway, "_ensure_enhancer_download", downloads.append)
    monkeypatch.setattr(gateway, "_enhance_prompt", lambda *args: (_ for _ in ()).throw(
        AssertionError("uncached enhancer must not load during an image request")))
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs:
                        (prompts.append(kwargs["prompt"]), FakeImage())[1])

    async def scenario():
        base = request_kwargs()
        result = await gateway._generate_response(**base, enhance_prompt=True)
        assert prompts == [base["prompt"]]
        assert result["enhancer_fallback"] is True
        assert downloads == [gateway.PE_T2I_ID]

    asyncio.run(scenario())


def test_startup_and_original_never_download_optional_checkpoints(monkeypatch):
    monkeypatch.setattr(gateway, "TOKEN", "test-token")
    monkeypatch.setattr(gateway, "_load_pipeline", lambda: None)
    monkeypatch.setattr(gateway.state, "torch", None)
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs: FakeImage())

    async def unexpected_download(model_id):
        raise AssertionError("Original must not download optional weights")

    monkeypatch.setattr(gateway, "_download_enhancer", unexpected_download)

    async def scenario():
        async with gateway.lifespan(gateway.app):
            result = await gateway._generate_response(**request_kwargs(), enhance_prompt=False)
            assert result["enhancer_fallback"] is False
            assert not gateway.enhancer_downloads
            assert not gateway.enhancer_ready
        assert not gateway.enhancer_downloads

    asyncio.run(scenario())


@pytest.mark.parametrize("editing", [False, True])
def test_only_requested_enhancer_downloads_once_then_is_used(monkeypatch, editing):
    requested = gateway.PE_I2I_ID if editing else gateway.PE_T2I_ID
    other = gateway.PE_T2I_ID if editing else gateway.PE_I2I_ID
    monkeypatch.setattr(gateway, "TOKEN", "test-token")
    monkeypatch.setattr(gateway, "_load_pipeline", lambda: None)
    monkeypatch.setattr(gateway.state, "torch", None)
    monkeypatch.setattr(gateway, "_run_pipeline", lambda **kwargs: FakeImage())
    monkeypatch.setattr(gateway, "_enhance_prompt", lambda prompt, images: PromptEnhancement("enhanced", requested))
    calls = []

    async def scenario():
        release = asyncio.Event()

        async def download(model_id):
            calls.append(model_id)
            await release.wait()
            gateway.enhancer_ready.add(model_id)

        monkeypatch.setattr(gateway, "_download_enhancer", download)
        async with gateway.lifespan(gateway.app):
            for _ in range(2):
                result = await gateway._generate_response(**request_kwargs(editing=editing), enhance_prompt=True)
                assert result["enhancer_fallback"] is True
            assert calls == [requested]
            assert other not in gateway.enhancer_downloads
            assert len(gateway.enhancer_downloads) == 1
            pending = tuple(gateway.enhancer_downloads.values())
            release.set()
            await asyncio.gather(*pending)
            result = await gateway._generate_response(**request_kwargs(editing=editing), enhance_prompt=True)
            assert result["prompt_enhanced"] is True
            assert result["enhancer_fallback"] is False
            assert calls == [requested]
        assert not gateway.enhancer_downloads

    asyncio.run(scenario())


def test_shutdown_cleans_pending_download_tasks(monkeypatch):
    monkeypatch.setattr(gateway, "TOKEN", "test-token")
    monkeypatch.setattr(gateway, "_load_pipeline", lambda: None)
    monkeypatch.setattr(gateway.state, "torch", None)
    cancelled = []

    async def pending(model_id):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(model_id)
            raise

    monkeypatch.setattr(gateway, "_download_enhancer", pending)

    async def scenario():
        async with gateway.lifespan(gateway.app):
            gateway._ensure_enhancer_download(gateway.PE_T2I_ID)
            await asyncio.sleep(0)
        assert cancelled == [gateway.PE_T2I_ID]
        assert not gateway.enhancer_downloads
        assert gateway.state.pipe is None

    asyncio.run(scenario())


def test_failed_download_is_not_marked_cached(monkeypatch):
    def failed(model_id):
        raise RuntimeError("test download failed")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=failed))
    asyncio.run(gateway._download_enhancer(gateway.PE_T2I_ID))
    assert gateway.PE_T2I_ID not in gateway.enhancer_ready
