"""CPU-only contract tests; real GPU inference needs a rented instance."""
import asyncio
import contextlib
import sys
from types import SimpleNamespace

import pytest

from pixelpilot.domain import GpuOffer, ReferenceImage
from pixelpilot.pricing import offer_quality_rank
from pixelpilot.services.inference_client import InferenceClient, InferenceError
from pixelpilot.services.vision_runtime import (
    COMMUNITY_TEXT_MODEL_ID, is_text_only_chat_model, load_chat_model, run_chat,
)


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


def test_community_checkpoint_loads_with_text_only_transformers(monkeypatch):
    """The community qwen3_5_text checkpoint needs AutoModelForCausalLM."""
    loaded = []
    model = SimpleNamespace(eval=lambda: None)

    class FakeCausalLM:
        @staticmethod
        def from_pretrained(path, **kwargs):
            loaded.append(("model", path, kwargs))
            return SimpleNamespace(eval=lambda: model)

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(path):
            loaded.append(("tokenizer", path))
            return "text-tokenizer"

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        bfloat16="bf16", cuda=SimpleNamespace(is_available=lambda: True),
    ))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoModelForCausalLM=FakeCausalLM, AutoTokenizer=FakeTokenizer,
    ))
    monkeypatch.setattr("pixelpilot.services.model_cache.prepare_model", lambda model_id: "/cache/community")
    assert is_text_only_chat_model(COMMUNITY_TEXT_MODEL_ID)
    assert not is_text_only_chat_model("Qwen/Qwen3.5-9B")
    actual_model, tokenizer = load_chat_model(COMMUNITY_TEXT_MODEL_ID)
    assert actual_model is model and tokenizer == "text-tokenizer"
    assert loaded[0] == ("tokenizer", "/cache/community")
    assert loaded[1][0:2] == ("model", "/cache/community")
    assert loaded[1][2]["device_map"] == "auto"


def test_text_only_chat_uses_string_messages_without_hidden_system_prompt(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        inference_mode=contextlib.nullcontext,
    ))

    class Inputs(dict):
        def to(self, device):
            return self

    class Tokenizer:
        eos_token_id = 248044
        pad_token_id = 248045

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            assert messages == [
                {"role": "user", "content": "السلام عليكم"},
                {"role": "assistant", "content": "وعليكم السلام"},
                {"role": "user", "content": "اشرح باختصار"},
            ]
            return Inputs(input_ids=SimpleNamespace(shape=(1, 2)))

        def decode(self, ids, **kwargs):
            assert ids == [13]
            return "هذا شرح مختصر"

    class Model:
        device = "cuda"

        def generate(self, **kwargs):
            assert kwargs["max_new_tokens"] == 1024
            assert kwargs["do_sample"] is True
            assert kwargs["temperature"] == 0.7
            assert kwargs["top_p"] == 0.8
            assert kwargs["top_k"] == 20
            assert kwargs["repetition_penalty"] == 1.1
            assert kwargs["eos_token_id"] == 248044
            assert kwargs["pad_token_id"] == 248045
            assert kwargs["stop_strings"] == ["<|im_start|>", "\nuser\n", "\nassistant\n"]
            assert isinstance(kwargs["tokenizer"], Tokenizer)
            return [[10, 11, 13]]

    assert run_chat(Model(), Tokenizer(), history=[
        {"role": "user", "content": "السلام عليكم"},
        {"role": "assistant", "content": "وعليكم السلام"},
    ], prompt="اشرح باختصار", images=[], max_new_tokens=1024, text_only=True) == "هذا شرح مختصر"
    with pytest.raises(ValueError, match="image"):
        run_chat(Model(), Tokenizer(), history=[], prompt="ما الصورة؟",
                 images=[object()], max_new_tokens=1024, text_only=True)


def test_text_only_chat_drops_fake_conversation_before_saving_history(monkeypatch):
    """A bad checkpoint response should not poison subsequent dialogue turns."""
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        inference_mode=contextlib.nullcontext,
    ))

    class Inputs(dict):
        def to(self, device):
            return self

    class Tokenizer:
        eos_token_id = 248044
        pad_token_id = 248045

        def apply_chat_template(self, messages, **kwargs):
            return Inputs(input_ids=SimpleNamespace(shape=(1, 2)))

        def decode(self, ids, **kwargs):
            return "يا ريتي... هذا مفاجئ.\nuser\nايه\nassistant\nيا ريتي... هذا مفاجئ."

    class Model:
        device = "cuda"

        def generate(self, **kwargs):
            assert kwargs["do_sample"] is True
            assert kwargs["eos_token_id"] == 248044
            assert kwargs["stop_strings"]
            return [[10, 11, 13]]

    actual = run_chat(Model(), Tokenizer(), history=[], prompt="ايه",
                      images=[], max_new_tokens=1024, text_only=True)
    assert actual == "يا ريتي... هذا مفاجئ."
    assert "user" not in actual


def test_gateway_declines_vision_for_community_model(monkeypatch):
    from fastapi import HTTPException
    from pixelpilot import inference_gateway as g
    monkeypatch.setattr(g, "TOKEN", "test-token")
    monkeypatch.setattr(g, "CHAT_MODEL_ID", COMMUNITY_TEXT_MODEL_ID)
    async def scenario():
        with pytest.raises(HTTPException) as exc:
            await g.chat_completions(
                g.ChatRequest(prompt="اشرح الصورة", images=["AA=="]),
                authorization="Bearer test-token",
            )
        assert exc.value.status_code == 422
        assert "text-only" in exc.value.detail
    asyncio.run(scenario())


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
