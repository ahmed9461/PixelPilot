from __future__ import annotations

import asyncio
from pathlib import Path

from pixelpilot.config import Settings
from pixelpilot.preflight import run_external_preflight, run_local_preflight
from pixelpilot.services.vast_gateway import VastSdkGateway, build_offer_query


async def _main() -> int:
    settings = Settings()
    checks = run_local_preflight(settings, repo_root=Path(__file__).resolve().parents[1])
    if all(item.ok for item in checks):
        checks.extend(await run_external_preflight(settings))

    for check in checks:
        print(("PASS" if check.ok else "FAIL"), f"{check.name}: {check.detail}")

    if not all(item.ok for item in checks):
        return 1

    try:
        gateway = VastSdkGateway(
            settings.vast_api_key,
            worker_proxy_port=settings.worker_proxy_port,
        )
        query = build_offer_query(
            settings.vast_min_gpu_ram_gb,
            settings.vast_min_reliability,
            settings.vast_max_price_usd_hour,
            disk_gb=settings.vast_disk_gb,
            verified_only=settings.vast_verified_only,
            datacenter_only=settings.vast_datacenter_only,
            min_direct_ports=settings.vast_min_direct_ports,
            min_inet_down_mbps=settings.vast_min_inet_down_mbps,
        )
        offers = await gateway.search_offers(query, settings.vast_default_limit)
        print("PASS", f"Vast API/search: {len(offers)} matching offer(s)")
    except Exception as exc:
        print("FAIL", f"Vast API/search: {type(exc).__name__}: {exc}")
        return 1
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
