"""CPU-only contract tests; real GPU inference needs a rented instance."""
import asyncio
import contextlib
import sys
from types import SimpleNamespace

import pytest

from pixelpilot.domain import GpuOffer, ReferenceImage
from pixelpilot.pricing import offer_quality_rank
from pixelpilot.services.inference_client import InferenceClient, InferenceError
from pixelpilot.services.vision_runtime import run_chat


def test_chat_client_sends_image_bytes_and_uses_authenticated_endpoint(monkeypatch):
    class DummyResponse:
        def json(self):
            return {
                "choices": [{"message": {"content": "أرى أرنبًا صغيرًا"}}]
            }

    class StubClient(InferenceClient):
        async def _request(self, method, path, **kwargs):
            self.last = (method, path, kwargs)
            return DummyResponse()

    async def scenario():
        client = StubClient("http://example.test", "secret", "Qwen/Qwen-Image-2.1")
        reply = await client.chat(
            "اشرح الصورة", history=[{"role": "user", "content": "سلام"}],
            images=(ReferenceImage(b"abc"),),
        )
        assert reply == "أرى أرنبًا صغيرًا"
        assert client.last[0:2] == ("POST", "/v1/chat/completions")
        assert client.last[2]["json"]["images"] == ["YWJj"]
        assert client.last[2]["json"]["history"][0]["content"] == "سلام"

    asyncio.run(scenario())


def test_vision_runtime_removes_thinking_markup(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "torch",
        SimpleNamespace(inference_mode=contextlib.nullcontext),
    )

    class Inputs(dict):
        def to(self, device):
            return self

    class Processor:
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            assert messages[-1]["content"][0]["type"] == "image"
            return Inputs(input_ids=SimpleNamespace(shape=(1, 2)))
        def decode(self, ids, **kwargs):
            assert ids == [12]
            return "<think>private scratch</think>نعم، هذه صورة."

    class Model:
        device = "cuda"
        def generate(self, **kwargs):
            assert kwargs["max_new_tokens"] == 128
            return [[10, 11, 12]]

    reply = run_chat(
        Model(), Processor(),
        history=[{"role": "user", "content": "أهلًا"}],
        prompt="ما هذا؟", images=[object()], max_new_tokens=128,
    )
    assert reply == "نعم، هذه صورة."
    assert "private scratch" not in reply


def test_quality_rank_prefers_fast_premium_offer_under_equal_acceptable_price():
    slow = GpuOffer(
        1, "RTX 3090", 24, 0.20, 0.99, 20,
        inet_down_mbps=150, inet_up_mbps=90,
        download_usd_per_gb=0,
    )
    fast = GpuOffer(
        2, "H100", 80, 0.59, 0.995, 90,
        inet_down_mbps=1100, inet_up_mbps=500,
        download_usd_per_gb=0,
    )
    rank = lambda offer: offer_quality_rank(
        offer, hourly_cap=0.60, download_gb=70, billed_hours=1,
        preferred_down_mbps=500, preferred_up_mbps=200,
    )
    assert sorted([slow, fast], key=rank)[0].offer_id == 2


def test_gateway_registers_chat_endpoint_without_gpu_import():
    # Importing the gateway must not initialize CUDA on the controller.
    from pixelpilot.inference_gateway import app
    assert "/v1/chat/completions" in {route.path for route in app.routes}
