"""Worker safeguards: pre-body authentication and cancellation-safe threads."""
from __future__ import annotations

import asyncio
import secrets
from typing import Any, Callable

from starlette.responses import JSONResponse


async def run_thread_safely(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Do not release a caller's GPU lock while its Python thread still runs.

    Cancelling asyncio.to_thread alone does not stop CUDA/model work. Drain the
    shielded task (also on repeated cancellation), then propagate cancellation.
    Never retry inference: a retry could duplicate work and downloads.
    """
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            cancelled = True
            if task.done():
                # Retrieve an exception as well as a successful result.
                try:
                    task.result()
                except BaseException:
                    pass
                raise
        except Exception:
            if cancelled:
                raise asyncio.CancelledError() from None
            raise
    if cancelled:
        raise asyncio.CancelledError()
    return result


class AuthenticatedBodyLimit:
    """Authenticate before FastAPI parses JSON or spools multipart files.

    Read at most max_bytes and replay the bounded original ASGI chunks. This
    catches chunked requests and forged Content-Length headers too. Nothing is
    written to disk by this middleware and response errors do not echo inputs.
    """
    def __init__(self, app: Any, *, token: Callable[[], str], max_bytes: int):
        self.app, self.token, self.max_bytes = app, token, max_bytes

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        secret = self.token()
        expected = f"Bearer {secret}".encode()
        provided = headers.get(b"authorization", b"")
        if not secret or not secrets.compare_digest(provided, expected):
            status = 503 if not secret else 401
            await JSONResponse({"detail": "Unavailable" if status == 503 else "Unauthorized"}, status_code=status)(scope, receive, send)
            return
        length = headers.get(b"content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                declared = -1
            if declared < 0 or declared > self.max_bytes:
                await JSONResponse({"detail": "Invalid or oversized request body"}, status_code=413)(scope, receive, send)
                return
        chunks: list[dict] = []
        total = 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            total += len(event.get("body", b""))
            if total > self.max_bytes:
                await JSONResponse({"detail": "Request body is too large"}, status_code=413)(scope, receive, send)
                return
            chunks.append(event)
            if not event.get("more_body", False):
                break
        pending = iter(chunks)

        async def replay() -> dict:
            try:
                return next(pending)
            except StopIteration:
                return await receive()

        await self.app(scope, replay, send)
