import asyncio
from datetime import UTC, datetime, timedelta

from pixelpilot.db import Database
from pixelpilot.services.billing import (
    begin_billing,
    billing_snapshot,
    finalize_billing,
    last_billing_snapshot,
    pause_billing,
    resume_billing,
)


def test_billing_counts_exact_seconds_and_pauses(tmp_path):
    async def scenario():
        db = Database(tmp_path / "billing.sqlite3")
        await db.init()
        start = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
        await begin_billing(db, 0.50, now=start)

        first = await billing_snapshot(db, now=start + timedelta(minutes=30))
        assert first is not None
        assert first["active_seconds"] == 1800
        assert first["estimated_cost_usd"] == 0.25

        await pause_billing(db, now=start + timedelta(minutes=30))
        paused = await billing_snapshot(db, now=start + timedelta(hours=1))
        assert paused is not None
        assert paused["active_seconds"] == 1800
        assert paused["estimated_cost_usd"] == 0.25

        await resume_billing(db, now=start + timedelta(hours=1))
        resumed = await billing_snapshot(db, now=start + timedelta(hours=1, minutes=15))
        assert resumed is not None
        assert resumed["active_seconds"] == 2700
        assert resumed["estimated_cost_usd"] == 0.375

    asyncio.run(scenario())


def test_finalize_persists_last_snapshot_and_clears_current_meter(tmp_path):
    async def scenario():
        db = Database(tmp_path / "billing.sqlite3")
        await db.init()
        start = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
        await begin_billing(db, 0.40, now=start)

        final = await finalize_billing(db, now=start + timedelta(minutes=15))
        assert final is not None
        assert final["active_seconds"] == 900
        assert round(final["estimated_cost_usd"], 6) == 0.1
        assert await billing_snapshot(db, now=start + timedelta(minutes=20)) is None
        assert await last_billing_snapshot(db) == final

    asyncio.run(scenario())
