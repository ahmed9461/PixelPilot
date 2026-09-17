import asyncio
import httpx

from pixelpilot.services.inference_client import InferenceClient, _extract_text


def test_extract_text_supports_string_and_parts():
    assert _extract_text("مرحبا") == "مرحبا"
    assert _extract_text([{"type": "text", "text": "أهلًا"}, {"text": " بك"}]) == "أهلًا بك"


def test_chat_sends_only_supplied_conversation():
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
        assert client.payload == {"model": "model-id", "messages": messages, "max_tokens": 123}
        assert all(item.get("role") != "system" for item in client.payload["messages"])
    asyncio.run(scenario())
