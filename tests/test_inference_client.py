import asyncio
import httpx

from pixelpilot.services.inference_client import InferenceClient, _extract_text


def test_extract_text_supports_string_and_parts():
    assert _extract_text("مرحبا") == "مرحبا"
    assert _extract_text([{"type": "text", "text": "أهلًا"}, {"text": " بك"}]) == "أهلًا بك"


def test_chat_uses_stable_defaults_without_rewriting_messages():
    async def scenario():
        class CapturingClient(InferenceClient):
            def __init__(self):
                super().__init__("http://example.invalid", "secret", "model-id")
                self.payload = None
            async def _request(self, method, path, **kwargs):
                self.payload = kwargs.get("json")
                return httpx.Response(200, json={"model": "model-id", "choices": [{"message": {"role": "assistant", "content": "تمام"}, "finish_reason": "stop"}]})
        client = CapturingClient()
        messages = [{"role": "user", "content": "مرحبا"}]
        result = await client.chat(messages, max_tokens=123)
        assert result.text == "تمام"
        assert client.payload == {
            "model": "model-id",
            "messages": messages,
            "max_tokens": 123,
            "temperature": 0.0,
            "top_p": 1.0,
        }
        assert client.payload["messages"] is messages
    asyncio.run(scenario())


def test_chat_accepts_owner_selected_generation_controls():
    async def scenario():
        class CapturingClient(InferenceClient):
            def __init__(self):
                super().__init__("http://example.invalid", "secret", "model-id")
                self.payload = None
            async def _request(self, method, path, **kwargs):
                self.payload = kwargs.get("json")
                return httpx.Response(200, json={"model": "model-id", "choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        client = CapturingClient()
        await client.chat([{"role": "user", "content": "hi"}], max_tokens=777, temperature=0.4, top_p=0.8)
        assert client.payload["max_tokens"] == 777
        assert client.payload["temperature"] == 0.4
        assert client.payload["top_p"] == 0.8
    asyncio.run(scenario())
