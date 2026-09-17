from __future__ import annotations

import asyncio

from vastai import VastAI

from pixelpilot.config import get_settings
from pixelpilot.db import Database
from pixelpilot.services.billing import billing_snapshot
from pixelpilot.services.inference_client import InferenceClient
from pixelpilot.services.vast_gateway import VastSdkGateway


async def _call(client: VastAI, method: str, **kwargs):
    fn = getattr(client, method)
    return await asyncio.to_thread(fn, **kwargs)


def _fmt_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


async def main() -> None:
    settings = get_settings()
    if not settings.vast_api_key:
        raise SystemExit("VAST_API_KEY is not configured")

    db = Database(settings.database_path)
    await db.init()
    instance_id = await db.get("instance.id")
    if not instance_id:
        raise SystemExit("PixelPilot has no current instance id in its database")

    instance_id = int(instance_id)
    gateway = VastSdkGateway(settings.vast_api_key, worker_proxy_port=settings.inference_port)
    raw_client = VastAI(api_key=settings.vast_api_key, raw=True, quiet=True)

    print(f"PixelPilot live diagnostics — instance {instance_id}\n")

    ref = None
    print("===== INSTANCE =====")
    try:
        ref = await gateway.show_instance(instance_id)
        print(f"status: {ref.status}")
        print(f"public_ip: {ref.public_ip or 'not assigned'}")
        print(f"mapped_port: {ref.mapped_port or 'not mapped'}")
        status_msg = ref.raw.get("status_msg") if isinstance(ref.raw, dict) else None
        if status_msg:
            print(f"status_msg: {status_msg}")
    except Exception as exc:
        print(f"ERROR: {exc}")

    phase = await db.get("instance.phase", "unknown")
    print("\n===== PIXELPILOT STATE =====")
    print(f"phase: {phase}")
    print(f"model: {settings.model_id}")

    print("\n===== BILLING =====")
    billing = await billing_snapshot(db)
    if billing is None:
        print("billing meter: not started")
    else:
        print(f"active: {'yes' if billing['active'] else 'no'}")
        print(f"active_time: {_fmt_duration(float(billing['active_seconds']))}")
        print(f"elapsed_since_rent: {_fmt_duration(float(billing['elapsed_seconds']))}")
        print(f"rate: ${float(billing['price_per_hour']):.3f}/h")
        print(f"estimated_gpu_cost: ${float(billing['estimated_cost_usd']):.4f}")

    print("\n===== INFERENCE PROBE =====")
    token = await db.get("inference.token")
    url = await db.get("inference.url")
    if not url and ref and ref.public_ip and ref.mapped_port:
        scheme = "https" if settings.inference_use_https else "http"
        url = f"{scheme}://{ref.public_ip}:{ref.mapped_port}"

    healthy = False
    if not url:
        print("endpoint: not mapped yet")
    elif not token:
        print(f"endpoint: {url}")
        print("token: unavailable in controller database")
    else:
        print(f"endpoint: {url}")
        probe = InferenceClient(
            str(url),
            str(token),
            settings.model_id,
            verify_tls=settings.inference_verify_tls,
            timeout_seconds=10,
        )
        healthy = await probe.health()
        print(f"health: {'OK' if healthy else 'NOT READY'}")
        if healthy:
            try:
                models = await probe.models()
                print("models: " + (", ".join(models) if models else "none reported"))
            except Exception as exc:
                print(f"models: ERROR: {exc}")

    print("\n===== PROGRESS =====")
    if healthy:
        print("READY — the assistant endpoint is responding.")
    elif ref is None:
        print("UNKNOWN — instance details could not be read.")
    elif ref.status.lower() not in {"running", "ready"}:
        print(f"BOOTING — Vast instance status is {ref.status!r}.")
    elif not ref.public_ip or not ref.mapped_port:
        print("STARTING — the instance is running, waiting for the public service port.")
    else:
        print("PROVISIONING — the instance is running and mapped; the assistant runtime is still starting or loading.")

    print("\n===== VAST INSTANCE LOGS =====")
    try:
        logs = await _call(raw_client, "logs", instance_id=instance_id, tail=250)
        print(logs.rstrip() if isinstance(logs, str) else logs)
    except Exception as exc:
        print(f"UNAVAILABLE: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
