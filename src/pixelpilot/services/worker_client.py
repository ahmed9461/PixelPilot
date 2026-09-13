from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import httpx

from pixelpilot.domain import GenerationSpec, ImageRef


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        verify_tls: bool = False,
        timeout_seconds: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
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
            response = await client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
            response.raise_for_status()
            return response

    async def health(self) -> dict[str, Any]:
        response = await self._request("GET", "/health")
        return response.json()

    async def is_ready(self) -> bool:
        try:
            data = await self.health()
            return bool(data.get("ok") and data.get("comfy_ready") and data.get("models_ready", True))
        except Exception:
            return False

    async def submit(self, spec: GenerationSpec, *, filename_prefix: str) -> str:
        payload = spec.to_dict() | {"filename_prefix": filename_prefix}
        response = await self._request("POST", "/jobs", json=payload)
        data = response.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise WorkerError(f"Worker rejected generation: {data}")
        return str(prompt_id)

    async def job(self, prompt_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/jobs/{prompt_id}")
        return response.json()

    async def wait_job(self, prompt_id: str, timeout_seconds: int = 900, poll_seconds: float = 2.0) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            result = await self.job(prompt_id)
            status = result.get("status")
            if status == "completed":
                return result
            if status == "error":
                raise WorkerError(str(result.get("error") or "Generation failed"))
            await asyncio.sleep(poll_seconds)
        raise WorkerError(f"Generation {prompt_id} timed out")

    async def download_image(self, image: ImageRef) -> bytes:
        response = await self._request(
            "GET",
            "/images",
            params={"filename": image.filename, "subfolder": image.subfolder, "type": image.image_type},
        )
        return response.content
