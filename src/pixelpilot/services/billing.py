from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pixelpilot.db import Database


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


async def begin_billing(
    db: Database,
    price_per_hour: float,
    *,
    now: datetime | None = None,
) -> None:
    """Start a per-second active-rental meter for the current instance."""
    stamp = (now or _utc_now()).astimezone(UTC)
    iso = stamp.isoformat()
    await db.set("billing.started_at", iso)
    await db.set("billing.active_since", iso)
    await db.set("billing.active_seconds", 0.0)
    await db.set("billing.price_per_hour", float(price_per_hour))


async def pause_billing(db: Database, *, now: datetime | None = None) -> None:
    stamp = (now or _utc_now()).astimezone(UTC)
    active_since = _parse_timestamp(await db.get("billing.active_since"))
    if active_since is None:
        return
    accumulated = float(await db.get("billing.active_seconds", 0.0) or 0.0)
    accumulated += max(0.0, (stamp - active_since).total_seconds())
    await db.set("billing.active_seconds", accumulated)
    await db.set("billing.active_since", None)


async def resume_billing(db: Database, *, now: datetime | None = None) -> None:
    if await db.get("billing.active_since"):
        return
    stamp = (now or _utc_now()).astimezone(UTC)
    await db.set("billing.active_since", stamp.isoformat())


async def sync_billing_status(
    db: Database,
    status: str,
    *,
    now: datetime | None = None,
) -> None:
    """Reconcile the local meter with a known Vast instance status.

    Running/frozen instances incur GPU rental charges according to Vast's
    documented status semantics. Stopped instances do not. Transitional
    states are intentionally left alone because their billing boundary is not
    exposed precisely by the status API.
    """
    normalized = str(status or "").lower()
    if normalized in {"running", "frozen"}:
        await resume_billing(db, now=now)
    elif normalized == "stopped":
        await pause_billing(db, now=now)


async def billing_snapshot(
    db: Database,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    price = await db.get("billing.price_per_hour")
    started_at = _parse_timestamp(await db.get("billing.started_at"))
    if price is None or started_at is None:
        return None

    stamp = (now or _utc_now()).astimezone(UTC)
    active_seconds = float(await db.get("billing.active_seconds", 0.0) or 0.0)
    active_since = _parse_timestamp(await db.get("billing.active_since"))
    if active_since is not None:
        active_seconds += max(0.0, (stamp - active_since).total_seconds())

    elapsed_seconds = max(0.0, (stamp - started_at).total_seconds())
    price_per_hour = float(price)
    return {
        "started_at": started_at.isoformat(),
        "active": active_since is not None,
        "active_seconds": active_seconds,
        "elapsed_seconds": elapsed_seconds,
        "price_per_hour": price_per_hour,
        "estimated_cost_usd": active_seconds * price_per_hour / 3600.0,
        "measured_at": stamp.isoformat(),
    }


async def finalize_billing(
    db: Database,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    stamp = (now or _utc_now()).astimezone(UTC)
    await pause_billing(db, now=stamp)
    snapshot = await billing_snapshot(db, now=stamp)
    if snapshot is not None:
        await db.set("billing.last", snapshot)
    for key in (
        "billing.started_at",
        "billing.active_since",
        "billing.active_seconds",
        "billing.price_per_hour",
    ):
        await db.set(key, None)
    return snapshot


async def last_billing_snapshot(db: Database) -> dict[str, Any] | None:
    value = await db.get("billing.last")
    return value if isinstance(value, dict) else None
