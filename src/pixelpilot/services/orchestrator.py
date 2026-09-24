from __future__ import annotations

import asyncio
import secrets
import shlex
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GeneratedImage, GpuOffer, InstancePhase, ReferenceImage
from pixelpilot.services.billing import (
    begin_billing,
    billing_snapshot,
    finalize_billing,
    last_billing_snapshot,
    pause_billing,
    resume_billing,
    sync_billing_status,
)
from pixelpilot.services.inference_client import InferenceClient
from pixelpilot.services.vast_gateway import VastSdkGateway, build_offer_query


ProgressCallback = Callable[[str], Awaitable[None]]


class OrchestratorError(RuntimeError):
    pass


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        vast: VastSdkGateway,
        *,
        inference_factory: Callable[[str, str], InferenceClient] | None = None,
    ):
        self.settings = settings
        self.db = db
        self.vast = vast
        self._inference_factory = inference_factory or self._default_inference_factory
        self._inference_lock = asyncio.Lock()
        self._rent_lock = asyncio.Lock()
        self._control_lock = asyncio.Lock()

    def _default_inference_factory(self, url: str, token: str) -> InferenceClient:
        return InferenceClient(
            url,
            token,
            self.settings.model_id,
            verify_tls=self.settings.inference_verify_tls,
            timeout_seconds=self.settings.inference_request_timeout_seconds,
        )

    async def offers(self) -> list[GpuOffer]:
        query = build_offer_query(
            self.settings.vast_min_gpu_ram_gb,
            self.settings.vast_min_reliability,
            self.settings.vast_max_price_usd_hour,
            disk_gb=self.settings.vast_disk_gb,
            verified_only=self.settings.vast_verified_only,
            datacenter_only=self.settings.vast_datacenter_only,
            min_direct_ports=self.settings.vast_min_direct_ports,
            min_inet_down_mbps=self.settings.vast_min_inet_down_mbps,
        )
        rows = await self.vast.search_offers(
            query,
            self.settings.vast_default_limit,
            storage_gb=float(self.settings.vast_disk_gb),
        )
        # Prefer GPUs that can keep the full BF16 pipeline resident while still
        # keeping cheaper 24 GB offload-capable offers visible as fallbacks.
        rows.sort(
            key=lambda row: (
                row.gpu_ram_gb < self.settings.vast_preferred_gpu_ram_gb,
                row.price_per_hour,
                -(row.dlperf or 0.0),
            )
        )
        await self.db.set("offers.last", [row.public_dict() for row in rows])
        await self.db.set("offers.last_refreshed_at", datetime.now(UTC).isoformat())
        await self.db.event("offers.search", {"query": query, "count": len(rows)})
        return rows

    async def cached_offer(self, offer_id: int) -> GpuOffer | None:
        rows = await self.db.get("offers.last", [])
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and int(row.get("offer_id") or 0) == offer_id:
                return GpuOffer(**row)
        return None

    async def rent(self, offer_id: int) -> dict[str, Any]:
        async with self._rent_lock:
            return await self._rent_locked(offer_id)

    async def _rent_locked(self, offer_id: int) -> dict[str, Any]:
        self.settings.validate_rent_ready()
        current = await self.db.get("instance.id")
        if current:
            raise OrchestratorError(f"There is already an active instance: {current}")
        phase = await self.db.get("instance.phase", InstancePhase.NONE.value)
        if phase in {
            InstancePhase.RENTING.value,
            InstancePhase.BOOTING.value,
            InstancePhase.PROVISIONING.value,
            InstancePhase.READY.value,
            InstancePhase.STOPPING.value,
            InstancePhase.STOPPED.value,
            InstancePhase.DESTROYING.value,
        }:
            raise OrchestratorError(f"Instance lifecycle is already busy: {phase}")

        offer = await self.cached_offer(offer_id)
        if offer is None:
            raise OrchestratorError("Offer is not in the latest search results. Search again before renting.")
        if offer.price_per_hour > self.settings.vast_max_price_usd_hour:
            raise OrchestratorError("Offer price exceeds the configured hard maximum")
        if offer.gpu_ram_gb < self.settings.vast_min_gpu_ram_gb:
            raise OrchestratorError("Offer VRAM is below the configured minimum")

        inference_token = secrets.token_urlsafe(32)
        unique_label = f"PixelPilot-{secrets.token_hex(6)}"
        await self.db.set("instance.phase", InstancePhase.RENTING.value)
        await self.db.set("instance.pending_label", unique_label)
        await self.db.set("instance.offer", offer.public_dict())
        await self.db.set("inference.token", inference_token)
        await self.db.set("inference.url", None)

        env = self._build_vast_env(inference_token)
        onstart_cmd = self._build_onstart_cmd()
        result: dict[str, Any] | None = None
        create_error: Exception | None = None
        try:
            result = await self.vast.create_instance(
                offer_id,
                image=None if self.settings.vast_template_hash else self.settings.vast_docker_image,
                disk_gb=self.settings.vast_disk_gb,
                template_hash=self.settings.vast_template_hash,
                env=env,
                onstart_cmd=onstart_cmd,
                label=unique_label,
                cancel_unavail=self.settings.vast_cancel_unavailable,
            )
        except Exception as exc:
            create_error = exc

        instance_id = _extract_instance_id(result or {})
        if not instance_id:
            try:
                matches = await self.vast.find_instances_by_label(unique_label)
            except Exception as reconcile_exc:
                matches = []
                await self.db.event(
                    "instance.reconcile_failed",
                    {"label": unique_label, "error": str(reconcile_exc)},
                )
            if len(matches) == 1:
                instance_id = matches[0].instance_id
                await self.db.event(
                    "instance.reconciled",
                    {"instance_id": instance_id, "label": unique_label},
                )

        if not instance_id:
            await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event(
                "instance.rent_failed",
                {"offer_id": offer_id, "label": unique_label, "error": str(create_error or result)},
            )
            if create_error:
                raise OrchestratorError(
                    f"Vast create_instance failed and no matching instance was found: {create_error}"
                ) from create_error
            raise OrchestratorError(f"Could not determine instance id from Vast response: {result}")

        await self.db.set("instance.id", instance_id)
        await self.db.set("instance.label", unique_label)
        await self.db.set("instance.pending_label", None)
        await self.db.set("instance.phase", InstancePhase.BOOTING.value)
        await begin_billing(self.db, offer.price_per_hour)
        await self.db.event(
            "instance.rented",
            {
                "instance_id": instance_id,
                "offer_id": offer_id,
                "price_per_hour": offer.price_per_hour,
                "label": unique_label,
                "model_id": self.settings.model_id,
            },
        )
        return {"instance_id": instance_id, "raw": result or {}, "offer": offer.public_dict()}

    async def rent_and_prepare(
        self,
        offer_id: int,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        result = await self.rent(offer_id)
        try:
            await self.wait_until_ready(result["instance_id"], progress=progress)
            return result
        except Exception as exc:
            current_id = await self.db.get("instance.id")
            if not current_id or int(current_id) != int(result["instance_id"]):
                await self.db.event(
                    "instance.provision_cancelled",
                    {"instance_id": result["instance_id"], "error": str(exc)},
                )
                raise
            await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event(
                "instance.provision_failed",
                {"instance_id": result["instance_id"], "error": str(exc)},
            )
            if self.settings.vast_auto_destroy_on_provision_failure:
                try:
                    await self.destroy_current()
                except Exception as destroy_exc:
                    await self.db.event(
                        "instance.rollback_failed",
                        {"instance_id": result["instance_id"], "error": str(destroy_exc)},
                    )
            raise

    async def wait_until_ready(
        self,
        instance_id: int,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.inference_ready_timeout_seconds
        last_notice: str | None = None

        while loop.time() < deadline:
            current_id = await self.db.get("instance.id")
            if not current_id or int(current_id) != int(instance_id):
                raise OrchestratorError("Provisioning was cancelled because this instance is no longer current")

            ref = await self.vast.show_instance(instance_id)
            status = ref.status.lower()
            if status in {"running", "frozen", "stopped"}:
                await sync_billing_status(self.db, status)
            if status in {"exited", "error", "failed", "dead"}:
                raise OrchestratorError(f"Vast instance entered terminal state: {ref.status}")

            if status not in {"running", "ready"}:
                await self.db.set("instance.phase", InstancePhase.BOOTING.value)
                notice = f"Vast: {ref.status}"
            elif not ref.public_ip or not ref.mapped_port:
                await self.db.set("instance.phase", InstancePhase.PROVISIONING.value)
                notice = "السيرفر يعمل، بانتظار منفذ إنشاء الصور..."
            else:
                await self.db.set("instance.phase", InstancePhase.PROVISIONING.value)
                url = self._inference_url(ref.public_ip, ref.mapped_port)
                await self.db.set("inference.url", url)
                token = await self.db.get("inference.token")
                inference = self._inference_factory(url, str(token or ""))
                if await inference.is_ready():
                    await self.db.set("instance.phase", InstancePhase.READY.value)
                    await self._touch_activity()
                    await self.db.event(
                        "instance.ready",
                        {
                            "instance_id": instance_id,
                            "inference_url": _redact_url(url),
                            "model_id": self.settings.model_id,
                        },
                    )
                    if progress:
                        await progress("✅ محرك الصور جاهز.")
                    return
                notice = "السيرفر يعمل؛ جاري تحميل محرك إنشاء الصور..."

            if progress and notice != last_notice:
                await progress(notice)
                last_notice = notice
            await asyncio.sleep(self.settings.provision_poll_seconds)

        raise OrchestratorError(
            f"Image inference endpoint did not become ready within {self.settings.inference_ready_timeout_seconds}s"
        )

    async def stop_current(self) -> bool:
        async with self._control_lock:
            instance_id = await self.db.get("instance.id")
            if not instance_id:
                return False
            await self.db.set("instance.phase", InstancePhase.STOPPING.value)
            await self.vast.stop_instance(int(instance_id))
            await pause_billing(self.db)
            await self.db.set("instance.phase", InstancePhase.STOPPED.value)
            await self.db.event("instance.stopped", {"instance_id": instance_id})
            return True

    async def start_current(self, progress: ProgressCallback | None = None) -> bool:
        async with self._control_lock:
            instance_id = await self.db.get("instance.id")
            if not instance_id:
                return False
            await self.vast.start_instance(int(instance_id))
            await resume_billing(self.db)
            await self.db.set("instance.phase", InstancePhase.BOOTING.value)
        await self.wait_until_ready(int(instance_id), progress=progress)
        await self._touch_activity()
        return True

    async def destroy_current(self) -> bool:
        async with self._control_lock:
            instance_id = await self.db.get("instance.id")
            if not instance_id:
                return False
            await self.db.set("instance.phase", InstancePhase.DESTROYING.value)
            await self.vast.destroy_instance(int(instance_id))
            billing = await finalize_billing(self.db)
            await self.db.event(
                "instance.destroyed",
                {"instance_id": instance_id, "billing": billing},
            )
            for key, value in (
                ("instance.id", None),
                ("instance.phase", InstancePhase.NONE.value),
                ("instance.offer", None),
                ("instance.label", None),
                ("instance.pending_label", None),
                ("inference.url", None),
                ("inference.token", None),
                ("instance.last_activity_at", None),
                ("inference.active", False),
                ("generation.active", False),
            ):
                await self.db.set(key, value)
            return True

    async def current_state(self, *, probe_inference: bool = False) -> dict[str, Any]:
        instance_id = await self.db.get("instance.id")
        phase = await self.db.get("instance.phase", InstancePhase.NONE.value)
        offer = await self.db.get("instance.offer")
        state_data: dict[str, Any] = {
            "instance_id": instance_id,
            "phase": phase,
            "offer": offer,
            "model_id": self.settings.model_id,
        }
        if not instance_id:
            return state_data

        ref = await self.vast.show_instance(int(instance_id))
        if ref.status.lower() in {"running", "frozen", "stopped"}:
            await sync_billing_status(self.db, ref.status)
        state_data.update(
            {
                "vast_status": ref.status,
                "public_ip": ref.public_ip,
                "mapped_port": ref.mapped_port,
                "billing": await billing_snapshot(self.db),
            }
        )
        if probe_inference:
            try:
                inference = await self._current_inference()
                state_data["inference_ready"] = await inference.is_ready()
            except Exception:
                state_data["inference_ready"] = False
        return state_data

    async def generate_image(
        self,
        prompt: str,
        *,
        width: int,
        height: int,
        steps: int,
        seed: int | None = None,
        reference_images: tuple[ReferenceImage, ...] = (),
    ) -> GeneratedImage:
        if self._inference_lock.locked():
            raise OrchestratorError("يوجد طلب إنشاء صورة آخر قيد المعالجة حاليًا")

        if not prompt.strip():
            raise OrchestratorError("اكتب وصف الصورة أو تعليمات التعديل")
        if len(reference_images) > self.settings.image_max_reference_images:
            raise OrchestratorError(
                f"الحد الأقصى للصور المرجعية هو {self.settings.image_max_reference_images}"
            )

        async with self._inference_lock:
            phase = await self.db.get("instance.phase", InstancePhase.NONE.value)
            instance_id = await self.db.get("instance.id")
            if phase != InstancePhase.READY.value or not instance_id:
                raise OrchestratorError("السيرفر غير جاهز لإنشاء الصور")

            await self.db.set_many(
                {
                    "inference.active": True,
                    "generation.active": True,
                }
            )
            await self._touch_activity()
            try:
                inference = await self._current_inference()
                result = await inference.generate(
                    prompt,
                    width=width,
                    height=height,
                    steps=steps,
                    seed=seed,
                    reference_images=reference_images,
                )
                await self.db.event(
                    "image.generated",
                    {
                        "instance_id": int(instance_id),
                        "prompt_chars": len(prompt),
                        "reference_count": len(reference_images),
                        "width": result.width,
                        "height": result.height,
                        "steps": steps,
                        "seed": result.seed,
                        "model": result.model,
                    },
                )
                return result
            except Exception as exc:
                await self.db.event(
                    "image.failed",
                    {
                        "instance_id": int(instance_id),
                        "prompt_chars": len(prompt),
                        "reference_count": len(reference_images),
                        "error": str(exc),
                    },
                )
                raise
            finally:
                await self.db.set_many(
                    {
                        "inference.active": False,
                        "generation.active": False,
                    }
                )
                await self._touch_activity()

    async def recover_current(self) -> None:
        await self.db.set_many({"inference.active": False, "generation.active": False})

        instance_id = await self.db.get("instance.id")
        if not instance_id:
            pending_label = await self.db.get("instance.pending_label")
            if not pending_label:
                return
            try:
                matches = await self.vast.find_instances_by_label(str(pending_label))
            except Exception as exc:
                await self.db.event(
                    "instance.pending_recovery_failed",
                    {"label": pending_label, "error": str(exc)},
                )
                return
            if len(matches) != 1:
                await self.db.event(
                    "instance.pending_recovery_unresolved",
                    {"label": pending_label, "count": len(matches)},
                )
                return
            instance_id = matches[0].instance_id
            await self.db.set("instance.id", instance_id)
            await self.db.set("instance.label", pending_label)
            await self.db.set("instance.pending_label", None)
            await self.db.set("instance.phase", InstancePhase.BOOTING.value)
            await self.db.event(
                "instance.pending_recovered",
                {"instance_id": instance_id, "label": pending_label},
            )

        try:
            ref = await self.vast.show_instance(int(instance_id))
        except Exception as exc:
            await self.db.event(
                "instance.recovery_probe_failed",
                {"instance_id": instance_id, "error": str(exc)},
            )
            return

        status = ref.status.lower()
        if status in {"running", "frozen", "stopped"}:
            await sync_billing_status(self.db, status)
        if status == "stopped":
            await self.db.set("instance.phase", InstancePhase.STOPPED.value)
            return
        if status in {"exited", "error", "failed", "dead"}:
            await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event(
                "instance.recovery_terminal",
                {"instance_id": instance_id, "status": ref.status},
            )
            return

        try:
            await self.wait_until_ready(int(instance_id))
        except Exception as exc:
            current_id = await self.db.get("instance.id")
            if current_id and int(current_id) == int(instance_id):
                await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event(
                "instance.recovery_failed",
                {"instance_id": instance_id, "error": str(exc)},
            )

    async def last_billing_snapshot(self) -> dict[str, Any] | None:
        return await last_billing_snapshot(self.db)

    async def _touch_activity(self) -> None:
        stamp = datetime.now(UTC).isoformat()
        await self.db.set("instance.last_activity_at", stamp)
        await self.db.set("cost_guard.warned_instance", None)
        await self.db.set("cost_guard.warned_activity_at", None)

    async def _current_inference(self) -> InferenceClient:
        url = await self.db.get("inference.url")
        token = await self.db.get("inference.token")
        if not url or not token:
            raise OrchestratorError("Inference endpoint is not available")
        return self._inference_factory(str(url), str(token))

    def _inference_url(self, public_ip: str, mapped_port: int) -> str:
        scheme = "https" if self.settings.inference_use_https else "http"
        return f"{scheme}://{public_ip}:{mapped_port}"

    def _build_vast_env(self, inference_token: str) -> str:
        values = {
            "HF_TOKEN": self.settings.hf_token,
            "PIXELPILOT_INFERENCE_TOKEN": inference_token,
            "INFERENCE_PORT": str(self.settings.inference_port),
            "MODEL_ID": self.settings.model_id,
            "MODEL_DTYPE": self.settings.model_dtype,
            "IMAGE_MEMORY_MODE": self.settings.image_memory_mode,
            "IMAGE_FULL_GPU_MIN_VRAM_GB": str(self.settings.image_full_gpu_min_vram_gb),
            "IMAGE_VAE_TILING": str(self.settings.image_vae_tiling).lower(),
            "IMAGE_VAE_SLICING": str(self.settings.image_vae_slicing).lower(),
            "IMAGE_MAX_REFERENCE_IMAGES": str(self.settings.image_max_reference_images),
            "IMAGE_MAX_UPLOAD_MB": str(self.settings.image_max_upload_mb),
            "HF_HOME": "/workspace/hf-cache",
            "DATA_DIRECTORY": "/workspace",
        }
        if self.settings.pixelpilot_repo_url:
            values["PIXELPILOT_REPO_URL"] = self.settings.pixelpilot_repo_url
            values["PIXELPILOT_REPO_REF"] = self.settings.pixelpilot_repo_ref

        parts = [
            f"-e {shlex.quote(f'{key}={value}')}"
            for key, value in values.items()
            if value != ""
        ]
        parts.append(f"-p {self.settings.inference_port}:{self.settings.inference_port}")
        return " ".join(parts)

    def _build_onstart_cmd(self) -> str | None:
        if not self.settings.pixelpilot_repo_url:
            return None
        root = "/workspace/PixelPilot"
        repo = shlex.quote(self.settings.pixelpilot_repo_url)
        ref = shlex.quote(self.settings.pixelpilot_repo_ref)
        return (
            f"if [ ! -d {root}/.git ]; then "
            f"git clone --depth 1 --branch {ref} {repo} {root}; "
            f"else git -C {root} fetch --depth 1 origin {ref} && git -C {root} reset --hard FETCH_HEAD; fi; "
            f"nohup bash {root}/scripts/bootstrap_vast.sh > /workspace/pixelpilot-bootstrap.log 2>&1 &"
        )


def _extract_instance_id(result: dict[str, Any]) -> int | None:
    for key in ("new_contract", "instance_id", "id", "contract_id"):
        value = result.get(key)
        if isinstance(value, dict):
            for nested in ("id", "instance_id"):
                if value.get(nested):
                    return int(value[nested])
        elif value:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def _redact_url(url: str) -> str:
    return url.split("?", 1)[0]
