import asyncio
import httpx

from pixelpilot.services.inference_client import InferenceClient, _extract_stream_delta, _extract_text


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
            "repetition_penalty": 1.0,
            "top_k": 20,
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
        await client.chat([{"role": "user", "content": "hi"}], max_tokens=777, temperature=0.4, top_p=0.8, repetition_penalty=1.16, top_k=25)
        assert client.payload["max_tokens"] == 777
        assert client.payload["temperature"] == 0.4
        assert client.payload["top_p"] == 0.8
        assert client.payload["repetition_penalty"] == 1.16
        assert client.payload["top_k"] == 25
    asyncio.run(scenario())



def test_stream_payload_and_sse_delta_parser():
    client = InferenceClient("http://example.invalid", "secret", "model-id")
    messages = [{"role": "user", "content": "مرحبا"}]
    payload = client._chat_payload(
        messages,
        max_tokens=321,
        temperature=0.2,
        top_p=0.9,
        repetition_penalty=1.1,
        top_k=20,
        stream=True,
    )
    assert payload == {
        "model": "model-id",
        "messages": messages,
        "max_tokens": 321,
        "temperature": 0.2,
        "top_p": 0.9,
        "repetition_penalty": 1.1,
        "top_k": 20,
        "stream": True,
    }
    assert _extract_stream_delta(
        'data: {"choices":[{"delta":{"content":"أهل"}}]}'
    ) == "أهل"
    assert _extract_stream_delta(
        'data: {"choices":[{"delta":{"content":[{"type":"text","text":"اً"}]}}]}'
    ) == "اً"
    assert _extract_stream_delta("data: [DONE]") is None
    assert _extract_stream_delta("event: ping") is None



def test_audio_transcription_uses_gateway_endpoint():
    async def scenario():
        class CapturingClient(InferenceClient):
            def __init__(self):
                super().__init__("http://example.invalid", "secret", "model-id")
                self.method = None
                self.path = None
                self.kwargs = None

            async def _request(self, method, path, **kwargs):
                self.method = method
                self.path = path
                self.kwargs = kwargs
                return httpx.Response(200, json={"text": "مرحبا من الصوت"})

        client = CapturingClient()
        text = await client.transcribe_audio(b"audio-bytes", mime_type="audio/ogg")
        assert text == "مرحبا من الصوت"
        assert client.method == "POST"
        assert client.path == "/v1/audio/transcriptions"
        assert client.kwargs["data"]["model"] == "turbo"
        file_tuple = client.kwargs["files"]["file"]
        assert file_tuple[1] == b"audio-bytes"
        assert file_tuple[2] == "audio/ogg"

    asyncio.run(scenario())
