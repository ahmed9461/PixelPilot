from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pixelpilot.domain import InferenceResult, InstancePhase
from pixelpilot.services.orchestrator import Orchestrator, OrchestratorError


async def chat_with_options(
    orchestrator: Orchestrator,
    messages: list[dict[str, Any]],
    *,
    generation: dict[str, Any],
) -> InferenceResult:
    """Run one chat request with owner-selected generation controls.

    This mirrors Orchestrator.chat while allowing the Telegram-side assistant
    profile to choose safe sampling values without mutating global .env state.
    """
    if orchestrator._inference_lock.locked():
        raise OrchestratorError("يوجد طلب آخر قيد المعالجة حاليًا")

    async with orchestrator._inference_lock:
        phase = await orchestrator.db.get("instance.phase", InstancePhase.NONE.value)
        instance_id = await orchestrator.db.get("instance.id")
        if phase != InstancePhase.READY.value or not instance_id:
            raise OrchestratorError("السيرفر غير جاهز للمحادثة")

        await orchestrator.db.set("inference.active", True)
        await orchestrator._touch_activity()
        try:
            inference = await orchestrator._current_inference()
            result = await inference.chat(
                messages,
                max_tokens=int(generation.get("max_tokens") or orchestrator.settings.model_max_output_tokens),
                temperature=float(generation.get("temperature", 0.0)),
                top_p=float(generation.get("top_p", 1.0)),
                repetition_penalty=float(generation.get("repetition_penalty", 1.1)),
            )
            await orchestrator.db.event(
                "chat.completed",
                {
                    "instance_id": int(instance_id),
                    "message_count": len(messages),
                    "response_chars": len(result.text),
                    "model": result.model,
                    "temperature": float(generation.get("temperature", 0.0)),
                    "top_p": float(generation.get("top_p", 1.0)),
                    "repetition_penalty": float(generation.get("repetition_penalty", 1.1)),
                },
            )
            return result
        except Exception as exc:
            await orchestrator.db.event(
                "chat.failed",
                {"instance_id": int(instance_id), "error": str(exc)},
            )
            raise
        finally:
            await orchestrator.db.set("inference.active", False)
            await orchestrator._touch_activity()



async def stream_chat_with_options(
    orchestrator: Orchestrator,
    messages: list[dict[str, Any]],
    *,
    generation: dict[str, Any],
    on_partial: Callable[[str], Awaitable[None]] | None = None,
) -> InferenceResult:
    """Run one streamed chat request and report accumulated text as it arrives."""
    if orchestrator._inference_lock.locked():
        raise OrchestratorError("يوجد طلب آخر قيد المعالجة حاليًا")

    async with orchestrator._inference_lock:
        phase = await orchestrator.db.get("instance.phase", InstancePhase.NONE.value)
        instance_id = await orchestrator.db.get("instance.id")
        if phase != InstancePhase.READY.value or not instance_id:
            raise OrchestratorError("السيرفر غير جاهز للمحادثة")

        await orchestrator.db.set("inference.active", True)
        await orchestrator._touch_activity()
        chunks: list[str] = []
        try:
            inference = await orchestrator._current_inference()
            async for delta in inference.stream_chat(
                messages,
                max_tokens=int(generation.get("max_tokens") or orchestrator.settings.model_max_output_tokens),
                temperature=float(generation.get("temperature", 0.0)),
                top_p=float(generation.get("top_p", 1.0)),
                repetition_penalty=float(generation.get("repetition_penalty", 1.1)),
            ):
                chunks.append(delta)
                if on_partial is not None:
                    await on_partial("".join(chunks))

            text = "".join(chunks)
            if not text:
                raise OrchestratorError("لم يصل رد نصي من المساعد")

            result = InferenceResult(text=text, model=inference.model_id)
            await orchestrator.db.event(
                "chat.completed",
                {
                    "instance_id": int(instance_id),
                    "message_count": len(messages),
                    "response_chars": len(text),
                    "model": result.model,
                    "streamed": True,
                    "temperature": float(generation.get("temperature", 0.0)),
                    "top_p": float(generation.get("top_p", 1.0)),
                    "repetition_penalty": float(generation.get("repetition_penalty", 1.1)),
                },
            )
            return result
        except Exception as exc:
            await orchestrator.db.event(
                "chat.failed",
                {"instance_id": int(instance_id), "error": str(exc), "streamed": True},
            )
            raise
        finally:
            await orchestrator.db.set("inference.active", False)
            await orchestrator._touch_activity()
