from __future__ import annotations

from typing import Any

import httpx

from pixelpilot.domain import InferenceResult


class InferenceError(RuntimeError):
    pass


class InferenceClient:
    """Thin client for the OpenAI-compatible vLLM endpoint on the rented GPU."""

    def __init__(
        self,
        base_url: str,
        token: str,
        model_id: str,
        *,
        verify_tls: bool = False,
        timeout_seconds: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.model_id = model_id
        self.verify_tls = verify_tls
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            verify=self.verify_tls,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                **kwargs,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:1000]
                raise InferenceError(
                    f"Inference API returned HTTP {response.status_code}: {detail}"
                ) from exc
            return response

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/health")
            return 200 <= response.status_code < 300
        except Exception:
            return False

    async def models(self) -> list[str]:
        response = await self._request("GET", "/v1/models")
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [
            str(item.get("id"))
            for item in rows
            if isinstance(item, dict) and item.get("id")
        ]

    async def is_ready(self) -> bool:
        if not await self.health():
            return False
        try:
            models = await self.models()
        except Exception:
            return False
        return self.model_id in models or bool(models)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 2048,
    ) -> InferenceResult:
        # Deliberately no system/developer prompt is added here. The payload is
        # only the conversation supplied by PixelPilot's Telegram session.
        payload = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        response = await self._request("POST", "/v1/chat/completions", json=payload)
        data = response.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise InferenceError(f"Inference API returned no choices: {str(data)[:1000]}")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise InferenceError("Inference API returned an invalid choice")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise InferenceError("Inference API returned no assistant message")

        text = _extract_text(message.get("content"))
        if text == "":
            raise InferenceError("Model returned an empty text response")

        usage = data.get("usage")
        return InferenceResult(
            text=text,
            model=str(data.get("model") or self.model_id),
            finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") is not None else None,
            usage=usage if isinstance(usage, dict) else None,
        )


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    chunks.append(value)
        return "".join(chunks)
    return ""
