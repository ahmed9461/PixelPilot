from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from pixelpilot.domain import InferenceResult


class InferenceError(RuntimeError):
    pass


class InferenceClient:
    """Client for PixelPilot's authenticated inference gateway on the rented GPU."""

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

    async def transcribe_audio(
        self,
        data: bytes,
        *,
        mime_type: str,
        filename: str = "audio",
    ) -> str:
        response = await self._request(
            "POST",
            "/v1/audio/transcriptions",
            files={"file": (filename, data, mime_type)},
            data={"model": "turbo"},
        )
        payload = response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise InferenceError("Speech transcription returned no text")
        return text.strip()

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

    def _chat_payload(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repetition_penalty: float,
        top_k: int,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "repetition_penalty": float(repetition_penalty),
            "top_k": int(top_k),
        }
        if stream:
            payload["stream"] = True
        return payload

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 1.0,
        repetition_penalty: float = 1.0,
        top_k: int = 20,
    ) -> InferenceResult:
        # PixelPilot does not rewrite the supplied conversation here. Any
        # optional persona/style prompt is explicitly assembled by the
        # controller from the owner's in-bot settings before this call.
        payload = self._chat_payload(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            top_k=top_k,
        )
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


    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 1.0,
        repetition_penalty: float = 1.0,
        top_k: int = 20,
    ) -> AsyncIterator[str]:
        """Yield text deltas from vLLM's OpenAI-compatible SSE stream."""
        payload = self._chat_payload(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            top_k=top_k,
            stream=True,
        )
        async with httpx.AsyncClient(
            verify=self.verify_tls,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.is_error:
                    body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                    raise InferenceError(
                        f"Inference API returned HTTP {response.status_code}: {body}"
                    )
                async for line in response.aiter_lines():
                    delta = _extract_stream_delta(line)
                    if delta is not None:
                        yield delta


def _extract_stream_delta(line: str) -> str | None:
    """Parse one OpenAI SSE line and return only assistant text deltas."""
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    delta = choices[0].get("delta")
    if not isinstance(delta, dict):
        return None
    text = _extract_text(delta.get("content"))
    return text or None


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
