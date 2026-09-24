from __future__ import annotations

import base64
from typing import Any

import httpx

from pixelpilot.domain import GeneratedImage, ReferenceImage


class InferenceError(RuntimeError):
    pass


class InferenceClient:
    """Client for PixelPilot's authenticated Qwen-Image gateway."""

    def __init__(
        self,
        base_url: str,
        token: str,
        model_id: str,
        *,
        verify_tls: bool = False,
        timeout_seconds: float = 1800.0,
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
                detail = response.text[:2000]
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
            return self.model_id in await self.models()
        except Exception:
            return False

    async def generate(
        self,
        prompt: str,
        *,
        width: int,
        height: int,
        steps: int,
        seed: int | None = None,
        reference_images: tuple[ReferenceImage, ...] = (),
        true_cfg_scale: float = 1.0,
        negative_prompt: str | None = None,
    ) -> GeneratedImage:
        if not prompt.strip():
            raise InferenceError("Prompt cannot be empty")

        common: dict[str, str] = {
            "prompt": prompt,
            "width": str(int(width)),
            "height": str(int(height)),
            "num_inference_steps": str(int(steps)),
            "true_cfg_scale": str(float(true_cfg_scale)),
        }
        if seed is not None:
            common["seed"] = str(int(seed))
        if negative_prompt is not None:
            common["negative_prompt"] = negative_prompt

        if reference_images:
            files = [
                (
                    "image",
                    (f"reference-{index + 1}.png", item.data, item.mime_type),
                )
                for index, item in enumerate(reference_images)
            ]
            response = await self._request(
                "POST",
                "/v1/images/edits",
                data=common,
                files=files,
            )
        else:
            payload: dict[str, Any] = {
                "prompt": prompt,
                "width": int(width),
                "height": int(height),
                "num_inference_steps": int(steps),
                "true_cfg_scale": float(true_cfg_scale),
            }
            if seed is not None:
                payload["seed"] = int(seed)
            if negative_prompt is not None:
                payload["negative_prompt"] = negative_prompt
            response = await self._request(
                "POST",
                "/v1/images/generations",
                json=payload,
            )

        data = response.json()
        if not isinstance(data, dict):
            raise InferenceError("Image endpoint returned an invalid response")
        encoded = data.get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise InferenceError("Image endpoint returned no image data")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise InferenceError("Image endpoint returned invalid base64") from exc

        return GeneratedImage(
            data=raw,
            mime_type=str(data.get("mime_type") or "image/png"),
            seed=int(data.get("seed") or 0),
            width=int(data.get("width") or width),
            height=int(data.get("height") or height),
            model=str(data.get("model") or self.model_id),
            reference_count=int(data.get("reference_count") or len(reference_images)),
        )
