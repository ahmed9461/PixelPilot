from __future__ import annotations

import asyncio
from typing import Any

import httpx

from pixelpilot.workflow import extract_history_images, history_error


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def system_stats(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/system_stats")
            response.raise_for_status()
            return response.json()

    async def models(self, folder: str) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/models/{folder}")
            response.raise_for_status()
            data = response.json()
        if isinstance(data, list):
            return [str(x) for x in data]
        return []

    async def is_ready(self) -> bool:
        try:
            data = await self.system_stats()
            return isinstance(data, dict)
        except Exception:
            return False

    async def wait_ready(self, timeout_seconds: int = 1200, poll_seconds: float = 5.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            if await self.is_ready():
                return
            await asyncio.sleep(poll_seconds)
        raise ComfyError(f"ComfyUI did not become ready within {timeout_seconds}s")

    async def submit(self, workflow_api_json: dict[str, Any], client_id: str) -> str:
        payload = {"prompt": workflow_api_json, "client_id": client_id}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/prompt", json=payload)
            response.raise_for_status()
            data = response.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"ComfyUI rejected workflow: {data}")
        return str(prompt_id)

    async def history(self, prompt_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            return response.json()

    async def job_status(self, prompt_id: str) -> dict[str, Any]:
        data = await self.history(prompt_id)
        if prompt_id not in data:
            return {"status": "running", "images": []}
        item = data[prompt_id]
        if not isinstance(item, dict):
            return {"status": "running", "images": []}
        error = history_error(item)
        if error:
            return {"status": "error", "images": [], "error": error}
        images = extract_history_images(item)
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        completed = bool(status.get("completed")) or bool(images)
        return {"status": "completed" if completed else "running", "images": images}

    async def wait_job(self, prompt_id: str, timeout_seconds: int = 900, poll_seconds: float = 2.0) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            result = await self.job_status(prompt_id)
            if result["status"] == "completed":
                return result
            if result["status"] == "error":
                raise ComfyError(str(result.get("error") or "ComfyUI generation failed"))
            await asyncio.sleep(poll_seconds)
        raise ComfyError(f"Generation {prompt_id} timed out")

    async def download_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": image_type}
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(f"{self.base_url}/view", params=params)
            response.raise_for_status()
            return response.content
