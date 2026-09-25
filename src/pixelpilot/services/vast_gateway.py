from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from pixelpilot.domain import GpuOffer, InstanceRef


class VastError(RuntimeError):
    pass


class VastCreateRejected(VastError):
    """Vast explicitly rejected an instance creation request."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Vast rejected instance creation: {reason}")


def build_offer_query(
    min_gpu_ram_gb: int,
    min_reliability: float,
    max_price_usd_hour: float,
    *,
    disk_gb: int = 100,
    verified_only: bool = True,
    datacenter_only: bool = False,
    min_direct_ports: int = 2,
    min_inet_down_mbps: float = 0,
    min_cpu_ram_gb: int = 0,
) -> str:
    # Vast's CLI/SDK query language expresses gpu_ram in GiB-like user units
    # (for example: gpu_ram>=48), even though raw offer payloads expose
    # gpu_ram in MB. Do not multiply the query threshold by 1000 here.
    min_ram_gb = int(min_gpu_ram_gb)
    terms = [
        "num_gpus=1",
        "rentable=true",
        f"gpu_ram>={min_ram_gb}",
        f"reliability>={min_reliability:.4f}",
        f"dph_total<={max_price_usd_hour:.4f}",
        f"disk_space>={int(disk_gb)}",
    ]
    if verified_only:
        terms.append("verified=true")
    if datacenter_only:
        terms.append("datacenter=true")
    if min_cpu_ram_gb > 0:
        terms.append(f"cpu_ram>={int(min_cpu_ram_gb)}")
    if min_direct_ports > 0:
        terms.append(f"direct_port_count>={int(min_direct_ports)}")
    if min_inet_down_mbps > 0:
        terms.append(f"inet_down>={float(min_inet_down_mbps):.0f}")
    return " ".join(terms)


def _num(raw: dict[str, Any], *names: str, default: float = 0.0) -> float:
    for name in names:
        value = raw.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return default


def normalize_offer(raw: dict[str, Any]) -> GpuOffer:
    gpu_ram_mb = _num(raw, "gpu_ram", "gpu_ram_mb")
    reliability = raw.get("reliability", raw.get("reliability2"))
    if reliability is not None:
        reliability = float(reliability)
        if reliability > 1:
            reliability /= 100
    verified_raw = raw.get("verified")
    verified: bool | None = None
    if verified_raw is not None:
        verified = bool(verified_raw)
    elif raw.get("verification") is not None:
        verified = str(raw.get("verification")).lower() in {"verified", "true", "1"}
    return GpuOffer(
        offer_id=int(raw.get("id") or raw.get("ask_id") or 0),
        gpu_name=str(raw.get("gpu_name") or raw.get("gpu_display_name") or "Unknown GPU"),
        gpu_ram_gb=gpu_ram_mb / 1000 if gpu_ram_mb else _num(raw, "gpu_ram_gb"),
        price_per_hour=_num(raw, "dph_total", "dph_base", "price"),
        reliability=reliability,
        dlperf=_num(raw, "dlperf", default=0.0) or None,
        location=raw.get("geolocation") or raw.get("location"),
        inet_down_mbps=_num(raw, "inet_down", default=0.0) or None,
        disk_space_gb=_num(raw, "disk_space", default=0.0) or None,
        verified=verified,
        raw=raw,
    )


def _safe_error_text(value: Any, *, limit: int = 300) -> str:
    if value is None:
        return "Vast rejected the request"
    text = " ".join(str(value).split())
    if not text:
        return "Vast rejected the request"
    return text[:limit]


def _http_rejection_reason(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        return None
    # A gateway timeout or rate limiter is not proof that the request did not
    # reach Vast. Keep the label until reconciliation can establish the result.
    if not 400 <= status_code < 500 or status_code in {408, 429}:
        return None

    payload: Any = None
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        for key in ("msg", "message", "error", "detail", "reason"):
            if payload.get(key):
                return f"HTTP {status_code}: {_safe_error_text(payload.get(key))}"
    body = getattr(response, "text", None)
    if body:
        return f"HTTP {status_code}: {_safe_error_text(body)}"
    return f"HTTP {status_code}"


def _create_rejection_reason(mapped: dict[str, Any]) -> str | None:
    success = mapped.get("success")
    if success is False:
        for key in ("msg", "message", "error", "detail", "reason"):
            if mapped.get(key):
                return _safe_error_text(mapped.get(key))
        return "Vast reported success=false"

    if not any(mapped.get(key) for key in ("new_contract", "instance_id", "contract_id")):
        for key in ("error", "errors"):
            if mapped.get(key):
                return _safe_error_text(mapped.get(key))
    return None


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0]
        except json.JSONDecodeError:
            match = re.search(r"new_contract[^0-9]+([0-9]+)", value)
            if match:
                return {"new_contract": int(match.group(1))}
    return {}


def extract_mapped_port(raw: dict[str, Any], internal_port: int) -> int | None:
    candidates = [raw]
    for nested_key in ("instance", "instances"):
        nested = raw.get(nested_key)
        if isinstance(nested, dict):
            candidates.append(nested)
        elif isinstance(nested, list):
            candidates.extend(item for item in nested if isinstance(item, dict))
    key = f"{internal_port}/tcp"
    for source in candidates:
        ports = source.get("ports")
        if isinstance(ports, dict):
            mappings = ports.get(key) or ports.get(str(internal_port))
            if isinstance(mappings, list) and mappings:
                item = mappings[0]
                if isinstance(item, dict):
                    value = item.get("HostPort") or item.get("host_port")
                    if value:
                        return int(value)
            elif isinstance(mappings, dict):
                value = mappings.get("HostPort") or mappings.get("host_port")
                if value:
                    return int(value)
        value = source.get(f"VAST_TCP_PORT_{internal_port}") or source.get(f"vast_tcp_port_{internal_port}")
        if value:
            return int(value)
    return None


def _instance_ref_from_raw(raw: dict[str, Any], *, worker_proxy_port: int, fallback_id: int = 0) -> InstanceRef:
    status = str(
        raw.get("actual_status")
        or raw.get("intended_status")
        or raw.get("status")
        or raw.get("cur_state")
        or raw.get("state")
        or "unknown"
    )
    public_ip = raw.get("public_ipaddr") or raw.get("public_ip") or raw.get("ssh_host")
    instance_id = int(raw.get("id") or raw.get("instance_id") or fallback_id or 0)
    return InstanceRef(
        instance_id=instance_id,
        status=status,
        public_ip=str(public_ip) if public_ip else None,
        mapped_port=extract_mapped_port(raw, worker_proxy_port),
        raw=raw,
    )


def _extract_rows(value: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
            if isinstance(nested, dict):
                return [nested]
    return []


def _merge_nonempty(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    """Keep primary values, but fill missing/empty fields from a fallback row."""
    merged = dict(fallback)
    for key, value in primary.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


class VastSdkGateway:
    def __init__(self, api_key: str, *, worker_proxy_port: int = 8190):
        self.api_key = api_key
        self.worker_proxy_port = worker_proxy_port
        self._client: Any | None = None

    def _get_client(self):
        if self._client is None:
            try:
                from vastai import VastAI
            except ImportError as exc:
                raise VastError("Install the official Vast SDK: pip install vastai") from exc
            self._client = VastAI(api_key=self.api_key, raw=True, quiet=True)
        return self._client

    async def search_offers(
        self,
        query: str | dict[str, Any],
        limit: int = 8,
        *,
        storage_gb: float = 5.0,
        no_default: bool = False,
    ) -> list[GpuOffer]:
        """Run a fresh marketplace request and return the cheapest matches.

        Vast's SDK performs a live HTTP request for each search_offers() call;
        PixelPilot keeps only the returned snapshot for comparison/details.
        Ask the backend to sort by total hourly price and request a wider pool
        than the Telegram display size so local ranking is not limited to a
        small score-sorted subset.
        """
        client = self._get_client()
        display_limit = max(1, int(limit))
        backend_limit = max(32, min(200, display_limit * 8))
        try:
            result = await asyncio.to_thread(
                client.search_offers,
                query=query,
                order="dph_total",
                limit=backend_limit,
                storage=float(storage_gb),
                no_default=no_default,
            )
        except Exception as exc:
            raise VastError(f"Vast search failed: {exc}") from exc
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = []
        rows = result if isinstance(result, list) else result.get("offers", []) if isinstance(result, dict) else []
        offers = [normalize_offer(row) for row in rows if isinstance(row, dict)]
        offers = [x for x in offers if x.offer_id > 0]
        offers.sort(key=lambda x: (x.price_per_hour, -(x.dlperf or 0)))
        return offers[:display_limit]

    async def lookup_offer(self, offer_id: int, *, storage_gb: float) -> GpuOffer | None:
        """Query the actual ask ID, independent of the ranked discovery window."""
        if offer_id <= 0:
            return None
        # String discovery queries get verified/external/rentable defaults in
        # Vast's SDK. Structured queries also get rented=false unless defaults
        # are disabled. Keep the exact-ID lookup aligned with discovery while
        # sending the ID as an integer; post-lookup checks enforce our policy.
        rows = await self.search_offers(
            {
                "id": {"eq": int(offer_id)},
                "rentable": {"eq": True},
                "verified": {"eq": True},
                "external": {"eq": False},
            },
            1,
            storage_gb=storage_gb,
            no_default=True,
        )
        return next((row for row in rows if row.offer_id == offer_id), None)

    async def create_instance(self, offer_id: int, *, image: str | None, disk_gb: int, template_hash: str | None = None, env: str | None = None, onstart_cmd: str | None = None, label: str = "PixelPilot", cancel_unavail: bool = True) -> dict[str, Any]:
        client = self._get_client()
        kwargs: dict[str, Any] = {"id": offer_id, "disk": disk_gb, "label": label, "ssh": True, "direct": True, "cancel_unavail": cancel_unavail}
        if image:
            kwargs["image"] = image
        if template_hash:
            kwargs["template_hash"] = template_hash
        if env:
            kwargs["env"] = env
        if onstart_cmd:
            kwargs["onstart_cmd"] = onstart_cmd
        try:
            result = await asyncio.to_thread(client.create_instance, **kwargs)
        except Exception as exc:
            rejection = _http_rejection_reason(exc)
            if rejection:
                raise VastCreateRejected(rejection) from exc
            raise VastError(f"Vast create_instance failed: {exc}") from exc
        mapped = _coerce_mapping(result)
        if mapped:
            rejection = _create_rejection_reason(mapped)
            if rejection:
                raise VastCreateRejected(rejection)
            return mapped

        if isinstance(result, str):
            lowered = result.lower()
            if any(marker in lowered for marker in ("error", "unavailable", "not available", "failed")):
                raise VastCreateRejected(_safe_error_text(result))
        return {"result": result}

    async def show_instance(self, instance_id: int) -> InstanceRef:
        client = self._get_client()
        try:
            raw_result = await asyncio.to_thread(client.show_instance, id=instance_id)
        except Exception as exc:
            raise VastError(f"Vast show_instance failed: {exc}") from exc

        raw = _coerce_mapping(raw_result)
        rows = _extract_rows(raw, "instances", "instance")
        instance_raw = rows[0] if rows else raw
        ref = _instance_ref_from_raw(
            instance_raw,
            worker_proxy_port=self.worker_proxy_port,
            fallback_id=instance_id,
        )

        # During early boot some Vast responses can be sparse even though the
        # instance list already knows that the contract is running. Reconcile
        # against show_instances() so "unknown" does not stall provisioning.
        if ref.status.lower() == "unknown" or not ref.public_ip or not ref.mapped_port:
            try:
                all_instances = await asyncio.to_thread(client.show_instances)
            except Exception:
                all_instances = []
            fallback_row = next(
                (
                    row
                    for row in all_instances
                    if isinstance(row, dict)
                    and int(row.get("id") or row.get("instance_id") or 0) == int(instance_id)
                ),
                None,
            )
            if fallback_row:
                instance_raw = _merge_nonempty(instance_raw, fallback_row)
                ref = _instance_ref_from_raw(
                    instance_raw,
                    worker_proxy_port=self.worker_proxy_port,
                    fallback_id=instance_id,
                )

        mapped_port = ref.mapped_port or extract_mapped_port(raw, self.worker_proxy_port)
        return InstanceRef(
            instance_id=ref.instance_id or instance_id,
            status=ref.status,
            public_ip=ref.public_ip,
            mapped_port=mapped_port,
            raw=instance_raw,
        )

    async def find_instances_by_label(self, label: str, limit: int = 5) -> list[InstanceRef]:
        client = self._get_client()
        try:
            result = await asyncio.to_thread(client.show_instances)
        except Exception as exc:
            raise VastError(f"Vast instance reconciliation failed: {exc}") from exc
        rows = _extract_rows(result, "instances", "results")
        refs: list[InstanceRef] = []
        for row in rows:
            if str(row.get("label") or "") != label:
                continue
            ref = _instance_ref_from_raw(row, worker_proxy_port=self.worker_proxy_port)
            if ref.instance_id > 0:
                refs.append(ref)
            if len(refs) >= max(1, min(int(limit), 25)):
                break
        return refs

    async def start_instance(self, instance_id: int) -> None:
        await self._lifecycle("start_instance", instance_id)

    async def stop_instance(self, instance_id: int) -> None:
        await self._lifecycle("stop_instance", instance_id)

    async def destroy_instance(self, instance_id: int) -> None:
        await self._lifecycle("destroy_instance", instance_id)

    async def _lifecycle(self, method: str, instance_id: int) -> None:
        client = self._get_client()
        try:
            await asyncio.to_thread(getattr(client, method), id=instance_id)
        except Exception as exc:
            raise VastError(f"Vast {method} failed: {exc}") from exc
