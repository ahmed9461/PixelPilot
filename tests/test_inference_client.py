import asyncio
import base64

import httpx

from pixelpilot.domain import ReferenceImage
from pixelpilot.services.inference_client import InferenceClient


def test_generation_payload_preserves_prompt_exactly():
    async def scenario():
        class CapturingClient(InferenceClient):
            def __init__(self):
                super().__init__("http://example.invalid", "secret", "Qwen/Qwen-Image-2.1")
                self.path = None
                self.kwargs = None

            async def _request(self, method, path, **kwargs):
                self.path = path
                self.kwargs = kwargs
                return httpx.Response(
                    200,
                    json={
                        "b64_json": base64.b64encode(b"png").decode("ascii"),
                        "mime_type": "image/png",
                        "seed": 99,
                        "width": 1024,
                        "height": 1024,
                        "model": "Qwen/Qwen-Image-2.1",
                        "reference_count": 0,
                    },
                )

        prompt = "  ارسم قطة بلا أي تعديل على النص  "
        client = CapturingClient()
        result = await client.generate(prompt, width=1024, height=1024, steps=40, enhance_prompt=False)
        assert client.path == "/v1/images/generations"
        assert client.kwargs["json"]["prompt"] == prompt
        assert client.kwargs["json"]["enhance_prompt"] is False
        assert "system" not in client.kwargs["json"]
        assert result.data == b"png"
        assert result.seed == 99

    asyncio.run(scenario())


def test_edit_uses_multipart_and_multiple_reference_images():
    async def scenario():
        class CapturingClient(InferenceClient):
            def __init__(self):
                super().__init__("http://example.invalid", "secret", "Qwen/Qwen-Image-2.1")
                self.path = None
                self.kwargs = None

            async def _request(self, method, path, **kwargs):
                self.path = path
                self.kwargs = kwargs
                return httpx.Response(
                    200,
                    json={
                        "b64_json": base64.b64encode(b"edited").decode("ascii"),
                        "seed": 7,
                        "width": 896,
                        "height": 1152,
                        "model": "Qwen/Qwen-Image-2.1",
                        "reference_count": 2,
                    },
                )

        refs = (
            ReferenceImage(b"one", "image/jpeg"),
            ReferenceImage(b"two", "image/png"),
        )
        client = CapturingClient()
        result = await client.generate(
            "عدّل الإضاءة",
            width=896,
            height=1152,
            steps=40,
            reference_images=refs,
            enhance_prompt=True,
        )
        assert client.path == "/v1/images/edits"
        assert client.kwargs["data"]["prompt"] == "عدّل الإضاءة"
        assert client.kwargs["data"]["enhance_prompt"] == "true"
        assert len(client.kwargs["files"]) == 2
        assert result.reference_count == 2

    asyncio.run(scenario())


def test_ready_requires_configured_image_model():
    async def scenario():
        class ModelsClient(InferenceClient):
            def __init__(self, models):
                super().__init__("http://example.invalid", "secret", "Qwen/Qwen-Image-2.1")
                self._models = models

            async def health(self):
                return True

            async def models(self):
                return self._models

        assert await ModelsClient(["Qwen/Qwen-Image-2.1"]).is_ready() is True
        assert await ModelsClient(["Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"]).is_ready() is False

    asyncio.run(scenario())
