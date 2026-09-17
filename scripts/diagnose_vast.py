from __future__ import annotations

import asyncio
import json
from typing import Any

from vastai import VastAI

from pixelpilot.config import get_settings
from pixelpilot.db import Database
from pixelpilot.services.inference_client import InferenceClient
from pixelpilot.services.vast_gateway import extract_mapped_port


async def _call(client: VastAI, method: str, **kwargs):
    fn = getattr(client, method)
    return await asyncio.to_thread(fn, **kwargs)


def _coerce_instance(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        nested = value.get("instances") or value.get("instance")
        if isinstance(nested, dict):
            return nested
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            return nested[0]
        return value
    return {}


async def main() -> None:
    settings = get_settings()
    if not settings.vast_api_key:
        raise SystemExit("VAST_API_KEY is not configured")

    db = Database(settings.database_path)
    await db.init()
    instance_id = await db.get("instance.id")
    if not instance_id:
        raise SystemExit("PixelPilot has no current instance id in its database")

    client = VastAI(api_key=settings.vast_api_key, raw=True, quiet=True)
    print(f"PixelPilot live diagnostics — instance {instance_id}\n")

    info: dict[str, Any] = {}
    print("===== INSTANCE =====")
    try:
        info = _coerce_instance(await _call(client, "show_instance", id=int(instance_id)))
        if info:
            summary = {
                key: info.get(key)
                for key in (
                    "id",
                    "actual_status",
                    "intended_status",
                    "cur_state",
                    "status_msg",
                    "public_ipaddr",
                    "ssh_host",
                    "ssh_port",
                    "ports",
                    "onstart",
                )
                if info.get(key) is not None
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print("No structured instance data returned")
    except Exception as exc:
        print(f"ERROR: {exc}")

    print("\n===== PIXELPILOT STATE =====")
    print(f"phase: {await db.get('instance.phase', 'unknown')}")
    print(f"model: {settings.model_id}")

    print("\n===== INFERENCE PROBE =====")
    token = await db.get("inference.token")
    url = await db.get("inference.url")
    if not url and info:
        public_ip = info.get("public_ipaddr") or info.get("public_ip")
        mapped_port = extract_mapped_port(info, settings.inference_port)
        if public_ip and mapped_port:
            scheme = "https" if settings.inference_use_https else "http"
            url = f"{scheme}://{public_ip}:{mapped_port}"
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

    print("\n===== VAST INSTANCE LOGS =====")
    try:
        logs = await _call(client, "logs", INSTANCE_ID=int(instance_id), tail="250")
        print(logs.rstrip() if isinstance(logs, str) else logs)
    except Exception as exc:
        print(f"ERROR: {exc}")

    # Vast's execute API is intentionally constrained. Keep diagnostics to
    # documented commands instead of shell commands such as tail/ps/nvidia-smi.
    for title, command in (
        ("WORKSPACE LIST", "ls -lah /workspace"),
        ("WORKSPACE DISK USAGE", "du -d 2 -h /workspace"),
    ):
        print(f"\n===== {title} =====")
        try:
            output = await _call(client, "execute", id=int(instance_id), COMMAND=command)
            print(output.rstrip() if isinstance(output, str) else output)
        except Exception as exc:
            print(f"UNAVAILABLE: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
