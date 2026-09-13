from __future__ import annotations

import asyncio
import secrets
import shlex
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import (
    GenerationResult,
    GenerationSpec,
    GenerationStatus,
    GpuOffer,
    ImageRef,
    InstancePhase,
)
from pixelpilot.services.vast_gateway import VastSdkGateway, build_offer_query
from pixelpilot.services.worker_client import WorkerClient


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
        worker_factory: Callable[[str, str], WorkerClient] | None = None,
    ):
        self.settings = settings
        self.db = db
        self.vast = vast
        self._worker_factory = worker_factory or self._default_worker_factory
        self._generation_lock = asyncio.Lock()
        self._rent_lock = asyncio.Lock()
        self._control_lock = asyncio.Lock()

    def _default_worker_factory(self, url: str, token: str) -> WorkerClient:
        return WorkerClient(
            url,
            token,
            verify_tls=self.settings.worker_verify_tls,
            timeout_seconds=self.settings.worker_request_timeout_seconds,
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
        rows = await self.vast.search_offers(query, self.settings.vast_default_limit)
        await self.db.set("offers.last", [row.public_dict() for row in rows])
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

        worker_token = secrets.token_urlsafe(32)
        unique_label = f"PixelPilot-{secrets.token_hex(6)}"
        await self.db.set("instance.phase", InstancePhase.RENTING.value)
        await self.db.set("instance.pending_label", unique_label)
        await self.db.set("instance.offer", offer.public_dict())
        await self.db.set("worker.token", worker_token)
        await self.db.set("worker.url", None)

        env = self._build_vast_env(worker_token)
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
        await self.db.event(
            "instance.rented",
            {"instance_id": instance_id, "offer_id": offer_id, "price_per_hour": offer.price_per_hour, "label": unique_label},
        )
        return {"instance_id": instance_id, "raw": result or {}, "offer": offer.public_dict()}

    async def rent_and_prepare(self, offer_id: int, progress: ProgressCallback | None = None) -> dict[str, Any]:
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
            await self.db.event("instance.provision_failed", {"instance_id": result["instance_id"], "error": str(exc)})
            if self.settings.vast_auto_destroy_on_provision_failure:
                try:
                    await self.destroy_current()
                except Exception as destroy_exc:
                    await self.db.event(
                        "instance.rollback_failed",
                        {"instance_id": result["instance_id"], "error": str(destroy_exc)},
                    )
            raise

    async def wait_until_ready(self, instance_id: int, *, progress: ProgressCallback | None = None) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.provision_ready_timeout_seconds
        last_notice: str | None = None
        while loop.time() < deadline:
            current_id = await self.db.get("instance.id")
            if not current_id or int(current_id) != int(instance_id):
                raise OrchestratorError("Provisioning was cancelled because this instance is no longer current")
            ref = await self.vast.show_instance(instance_id)
            status = ref.status.lower()
            if status in {"exited", "error", "failed", "dead"}:
                raise OrchestratorError(f"Vast instance entered terminal state: {ref.status}")

            if status not in {"running", "ready"}:
                await self.db.set("instance.phase", InstancePhase.BOOTING.value)
                notice = f"Vast: {ref.status}"
            elif not ref.public_ip or not ref.mapped_port:
                await self.db.set("instance.phase", InstancePhase.PROVISIONING.value)
                notice = "السيرفر يعمل، بانتظار منفذ PixelPilot Worker..."
            else:
                await self.db.set("instance.phase", InstancePhase.PROVISIONING.value)
                url = self._worker_url(ref.public_ip, ref.mapped_port)
                await self.db.set("worker.url", url)
                token = await self.db.get("worker.token")
                worker = self._worker_factory(url, str(token or ""))
                if await worker.is_ready():
                    await self.db.set("instance.phase", InstancePhase.READY.value)
                    await self._touch_activity()
                    await self.db.event(
                        "instance.ready",
                        {"instance_id": instance_id, "worker_url": _redact_url(url)},
                    )
                    if progress:
                        await progress("✅ السيرفر جاهز بالكامل للتوليد.")
                    return
                notice = "السيرفر يعمل؛ جاري تنزيل/تحميل Krea وتشغيل ComfyUI..."

            if progress and notice != last_notice:
                await progress(notice)
                last_notice = notice
            await asyncio.sleep(self.settings.provision_poll_seconds)

        raise OrchestratorError(
            f"PixelPilot worker did not become ready within {self.settings.provision_ready_timeout_seconds}s"
        )

    async def stop_current(self) -> bool:
        async with self._control_lock:
            instance_id = await self.db.get("instance.id")
            if not instance_id:
                return False
            await self.db.set("instance.phase", InstancePhase.STOPPING.value)
            await self.vast.stop_instance(int(instance_id))
            await self.db.set("instance.phase", InstancePhase.STOPPED.value)
            await self.db.event("instance.stopped", {"instance_id": instance_id})
            return True

    async def start_current(self, progress: ProgressCallback | None = None) -> bool:
        async with self._control_lock:
            instance_id = await self.db.get("instance.id")
            if not instance_id:
                return False
            await self.vast.start_instance(int(instance_id))
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
            await self.db.event("instance.destroyed", {"instance_id": instance_id})
            for key, value in (
                ("instance.id", None),
                ("instance.phase", InstancePhase.NONE.value),
                ("instance.offer", None),
                ("instance.label", None),
                ("instance.pending_label", None),
                ("worker.url", None),
                ("worker.token", None),
                ("instance.last_activity_at", None),
                ("generation.active", False),
            ):
                await self.db.set(key, value)
            return True

    async def current_state(self, *, probe_worker: bool = False) -> dict[str, Any]:
        instance_id = await self.db.get("instance.id")
        phase = await self.db.get("instance.phase", InstancePhase.NONE.value)
        offer = await self.db.get("instance.offer")
        state: dict[str, Any] = {"instance_id": instance_id, "phase": phase, "offer": offer}
        if not instance_id:
            return state
        ref = await self.vast.show_instance(int(instance_id))
        state.update({"vast_status": ref.status, "public_ip": ref.public_ip, "mapped_port": ref.mapped_port})
        if probe_worker:
            try:
                worker = await self._current_worker()
                state["worker_ready"] = await worker.is_ready()
            except Exception:
                state["worker_ready"] = False
        return state

    async def generate(self, spec: GenerationSpec) -> GenerationResult:
        if self._generation_lock.locked():
            raise OrchestratorError("يوجد توليد آخر قيد التنفيذ حاليًا")
        async with self._generation_lock:
            await self.db.set("generation.active", True)
            await self._touch_activity()
            try:
                return await self._generate_locked(spec)
            finally:
                await self.db.set("generation.active", False)
                await self._touch_activity()

    async def _generate_locked(self, spec: GenerationSpec) -> GenerationResult:
        if spec.batch_size > self.settings.generation_max_batch:
            raise OrchestratorError(f"Batch cannot exceed {self.settings.generation_max_batch}")
        if spec.steps > self.settings.generation_max_steps:
            raise OrchestratorError(f"Steps cannot exceed {self.settings.generation_max_steps}")
        phase = await self.db.get("instance.phase", InstancePhase.NONE.value)
        instance_id = await self.db.get("instance.id")
        if phase != InstancePhase.READY.value or not instance_id:
            raise OrchestratorError("السيرفر غير جاهز للتوليد")

        generation_id = await self.db.create_generation(
            prompt=spec.prompt,
            seed=spec.seed,
            instance_id=int(instance_id),
            status=GenerationStatus.CREATED.value,
            result={"request": spec.to_dict(), "images": []},
        )
        worker = await self._current_worker()
        prefix = f"PixelPilot/g{generation_id}"
        try:
            prompt_id = await worker.submit(spec, filename_prefix=prefix)
            await self.db.update_generation(
                generation_id,
                status=GenerationStatus.SUBMITTED.value,
                prompt_id=prompt_id,
            )
            job = await worker.wait_job(
                prompt_id,
                timeout_seconds=self.settings.worker_generation_timeout_seconds,
            )
            images = [
                ImageRef(
                    filename=str(item["filename"]),
                    subfolder=str(item.get("subfolder") or ""),
                    image_type=str(item.get("type") or "output"),
                )
                for item in job.get("images", [])
                if isinstance(item, dict) and item.get("filename")
            ]
            if not images:
                raise OrchestratorError("ComfyUI completed but returned no images")
            result_json = {"request": spec.to_dict(), "images": [image.to_dict() for image in images]}
            await self.db.update_generation(
                generation_id,
                status=GenerationStatus.COMPLETED.value,
                prompt_id=prompt_id,
                result=result_json,
            )
            await self.db.event(
                "generation.completed",
                {"generation_id": generation_id, "prompt_id": prompt_id, "image_count": len(images)},
            )
            return GenerationResult(generation_id=generation_id, prompt_id=prompt_id, spec=spec, images=images)
        except Exception as exc:
            await self.db.update_generation(generation_id, status=GenerationStatus.ERROR.value)
            await self.db.event("generation.failed", {"generation_id": generation_id, "error": str(exc)})
            raise

    async def generation_record(self, generation_id: int) -> dict[str, Any] | None:
        return await self.db.get_generation(generation_id)

    async def download_generation_image(self, generation_id: int, index: int) -> tuple[bytes, ImageRef]:
        record = await self.db.get_generation(generation_id)
        if not record or not isinstance(record.get("result"), dict):
            raise OrchestratorError("Generation not found")
        images = record["result"].get("images") or []
        if index < 0 or index >= len(images):
            raise OrchestratorError("Image index out of range")
        image = ImageRef(**images[index])
        worker = await self._current_worker()
        return await worker.download_image(image), image

    async def regenerate(self, generation_id: int, *, same_seed: bool) -> GenerationResult:
        record = await self.db.get_generation(generation_id)
        if not record or not isinstance(record.get("result"), dict):
            raise OrchestratorError("Generation not found")
        request = record["result"].get("request")
        if not isinstance(request, dict):
            raise OrchestratorError("Generation request metadata is missing")
        spec = GenerationSpec(**request)
        if not same_seed:
            spec = GenerationSpec(**(spec.to_dict() | {"seed": secrets.randbits(63)}))
        return await self.generate(spec)

    async def recover_current(self) -> None:
        await self.db.set("generation.active", False)
        instance_id = await self.db.get("instance.id")
        if not instance_id:
            pending_label = await self.db.get("instance.pending_label")
            if not pending_label:
                return
            try:
                matches = await self.vast.find_instances_by_label(str(pending_label))
            except Exception as exc:
                await self.db.event("instance.pending_recovery_failed", {"label": pending_label, "error": str(exc)})
                return
            if len(matches) != 1:
                await self.db.event("instance.pending_recovery_unresolved", {"label": pending_label, "count": len(matches)})
                return
            instance_id = matches[0].instance_id
            await self.db.set("instance.id", instance_id)
            await self.db.set("instance.label", pending_label)
            await self.db.set("instance.pending_label", None)
            await self.db.set("instance.phase", InstancePhase.BOOTING.value)
            await self.db.event("instance.pending_recovered", {"instance_id": instance_id, "label": pending_label})
        try:
            ref = await self.vast.show_instance(int(instance_id))
        except Exception as exc:
            await self.db.event("instance.recovery_probe_failed", {"instance_id": instance_id, "error": str(exc)})
            return
        status = ref.status.lower()
        if status == "stopped":
            await self.db.set("instance.phase", InstancePhase.STOPPED.value)
            return
        if status in {"exited", "error", "failed", "dead"}:
            await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event("instance.recovery_terminal", {"instance_id": instance_id, "status": ref.status})
            return
        try:
            await self.wait_until_ready(int(instance_id))
        except Exception as exc:
            current_id = await self.db.get("instance.id")
            if current_id and int(current_id) == int(instance_id):
                await self.db.set("instance.phase", InstancePhase.ERROR.value)
            await self.db.event("instance.recovery_failed", {"instance_id": instance_id, "error": str(exc)})

    async def _touch_activity(self) -> None:
        stamp = datetime.now(UTC).isoformat()
        await self.db.set("instance.last_activity_at", stamp)
        await self.db.set("cost_guard.warned_instance", None)
        await self.db.set("cost_guard.warned_activity_at", None)

    async def _current_worker(self) -> WorkerClient:
        url = await self.db.get("worker.url")
        token = await self.db.get("worker.token")
        if not url or not token:
            raise OrchestratorError("Worker endpoint is not available")
        return self._worker_factory(str(url), str(token))

    def _worker_url(self, public_ip: str, mapped_port: int) -> str:
        scheme = "https" if self.settings.worker_use_https else "http"
        return f"{scheme}://{public_ip}:{mapped_port}"

    def _build_vast_env(self, worker_token: str) -> str:
        portal = f"localhost:{self.settings.worker_proxy_port}:{self.settings.worker_internal_port}:/health:PixelPilot Worker"
        values = {
            "HF_TOKEN": self.settings.hf_token,
            "PIXELPILOT_WORKER_TOKEN": worker_token,
            "OPEN_BUTTON_TOKEN": worker_token,
            "OPEN_BUTTON_PORT": str(self.settings.worker_proxy_port),
            "PORTAL_CONFIG": portal,
            "PIXELPILOT_TRUST_PROXY": "1",
            "PIXELPILOT_WORKER_PORT": str(self.settings.worker_internal_port),
            "COMFY_PORT": str(self.settings.comfy_port),
            "COMFY_URL": f"http://127.0.0.1:{self.settings.comfy_port}",
            "COMFYUI_REF": self.settings.comfyui_ref,
            "GENERATION_MAX_BATCH": str(self.settings.generation_max_batch),
            "GENERATION_MAX_STEPS": str(self.settings.generation_max_steps),
            "DATA_DIRECTORY": "/workspace",
        }
        if self.settings.pixelpilot_repo_url:
            values["PIXELPILOT_REPO_URL"] = self.settings.pixelpilot_repo_url
            values["PIXELPILOT_REPO_REF"] = self.settings.pixelpilot_repo_ref
        parts = [f"-e {shlex.quote(f'{key}={value}')}" for key, value in values.items() if value != ""]
        parts.append(f"-p {self.settings.worker_proxy_port}:{self.settings.worker_proxy_port}")
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
