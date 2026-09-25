import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pixelpilot.bot.routers import servers
from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GpuOffer
from pixelpilot.services.orchestrator import Orchestrator, OfferChangedError, OrchestratorError
from pixelpilot.services.vast_gateway import normalize_offer


def quote(offer_id=1, *, down=0.001, up=0.001, hour=0.4, vram=48):
    return GpuOffer(offer_id, "Test GPU", vram, hour, 0.99, 40,
                    machine_id=100 + offer_id,
                    download_usd_per_gb=down, upload_usd_per_gb=up)


class QuotesVast:
    def __init__(self, rows):
        self.rows = rows
        self.live = None
        self.searches = []
        self.lookups = []
        self.creates = []

    async def search_offers(self, query, limit, **kwargs):
        self.searches.append(query)
        # Deliberately ignore price filters: local defenses must still work.
        return [row for row in self.rows if row.gpu_ram_gb >= (48 if "gpu_ram>=48" in query else 24)]

    async def lookup_offer(self, offer_id, *, machine_id, storage_gb):
        self.lookups.append((offer_id, machine_id, storage_gb))
        return self.live or next(row for row in self.rows if row.offer_id == offer_id)

    async def create_instance(self, offer_id, **kwargs):
        self.creates.append((offer_id, kwargs))
        return {"new_contract": 321, "success": True}

    async def find_instances_by_label(self, label):
        return []


async def setup(tmp_path, rows, **overrides):
    settings = Settings(_env_file=None, database_path=tmp_path / "transfer.sqlite3",
                        pixelpilot_repo_url="https://example.invalid/PixelPilot.git", **overrides)
    db = Database(settings.database_path)
    await db.init()
    vast = QuotesVast(rows)
    return Orchestrator(settings, db, vast), vast, db


def test_gateway_normalization_preserves_raw_bandwidth_quote():
    row = normalize_offer({"id": 1, "machine_id": 11, "gpu_ram": 48000,
                           "dph_total": 0.4, "inet_down_cost": "0.026051779935275",
                           "inet_up_cost": 0})
    assert row.download_usd_per_gb == 0.026051779935275
    assert row.upload_usd_per_gb == 0
    assert row.public_dict()["download_usd_per_gb"] == row.download_usd_per_gb


def test_discovery_cost_ranking_and_preferred_only_remain_live(tmp_path):
    async def scenario():
        rows = [quote(1, down=0.03, hour=0.2), quote(2, down=0.001, hour=0.48),
                quote(3, down=0.002, hour=0.25, vram=24), quote(4, down=None, hour=0.1)]
        orch, vast, db = await setup(tmp_path, rows)
        assert [row.offer_id for row in await orch.offers()] == [3, 2, 1, 4]
        assert len(vast.searches) == 2
        saved = await orch.cached_offer(2)
        assert saved.download_usd_per_gb == 0.001
        assert saved.machine_id == 102
        assert [row.offer_id for row in await orch.offers(preferred_only=True)] == [2, 1, 4]
        assert len(vast.searches) == 3
        assert await db.get("offers.search_mode") == "preferred"
    asyncio.run(scenario())


@pytest.mark.parametrize("cap,expected,query_value", [(5, [1, 2], "0.005"), (0, [1], "0")])
def test_search_applies_rate_cap_in_query_and_locally(tmp_path, cap, expected, query_value):
    async def scenario():
        rows = [quote(1, down=0), quote(2, down=0.005), quote(3, down=0.006), quote(4, down=None)]
        orch, vast, _ = await setup(tmp_path, rows, vast_max_download_usd_per_tb=cap)
        assert [row.offer_id for row in await orch.offers()] == expected
        assert all(f"inet_down_cost<={query_value}" in query for query in vast.searches)
        assert not vast.creates
    asyncio.run(scenario())


@pytest.mark.parametrize("field,new_value", [
    ("download_usd_per_gb", 0.002), ("upload_usd_per_gb", 0.002),
    ("download_usd_per_gb", None), ("upload_usd_per_gb", None),
    ("download_usd_per_gb", 0), ("download_usd_per_gb", 0.001000000001),
])
def test_rate_change_alone_requires_new_confirmation(tmp_path, field, new_value):
    async def scenario():
        old = quote()
        orch, vast, db = await setup(tmp_path, [old])
        await orch.offers()
        vast.live = replace(old, **{field: new_value})
        with pytest.raises(OfferChangedError):
            await orch.rent(1)
        assert vast.lookups == [(1, 101, 100.0)]
        assert not vast.creates
        assert await db.get("instance.pending_label") is None
        assert await db.get("instance.id") is None
    asyncio.run(scenario())


@pytest.mark.parametrize("rate", [0.006, None])
def test_live_cap_recheck_blocks_even_unchanged_cached_quote(tmp_path, rate):
    async def scenario():
        selected = quote(down=rate)
        orch, vast, db = await setup(tmp_path, [selected], vast_max_download_usd_per_tb=5)
        await db.set("offers.last", [selected.public_dict()])
        with pytest.raises(OfferChangedError, match="Download"):
            await orch.rent(1)
        assert not vast.creates
        assert await db.get("instance.phase", "none") == "none"
        assert await db.get("instance.pending_label") is None
    asyncio.run(scenario())


def test_valid_quote_rents_same_id_once_with_cancel_unavailable(tmp_path):
    async def scenario():
        orch, vast, db = await setup(tmp_path, [quote(49299788, down=0.005)],
                                     vast_max_download_usd_per_tb=5)
        await orch.offers()
        result = await orch.rent(49299788)
        assert result["instance_id"] == 321
        assert vast.creates[0][0] == 49299788
        assert vast.creates[0][1]["cancel_unavail"] is True
        assert (await db.get("instance.offer"))["download_usd_per_gb"] == 0.005
        with pytest.raises(OrchestratorError):
            await orch.rent(49299788)
        assert len(vast.creates) == 1
    asyncio.run(scenario())


def test_telegram_details_disclose_transfer_before_confirmation(tmp_path, monkeypatch):
    async def scenario():
        orch, vast, _ = await setup(tmp_path, [quote(down=0.026)])
        await orch.offers()
        monkeypatch.setattr(servers, "_orchestrator", orch)
        messages = []

        async def edit(text, **kwargs):
            messages.append((text, kwargs))

        async def answer(*args, **kwargs):
            pass

        monkeypatch.setattr(servers, "safe_callback_answer", answer)
        callback = SimpleNamespace(data="servers:offer:1:a", message=SimpleNamespace(edit_text=edit))
        await servers.offer_details(callback)
        text, kwargs = messages[0]
        assert "$26/TB" in text and "$1.8200" in text
        assert "ليس فاتورة" in text
        assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "servers:rent:1:a"
        assert not vast.creates
    asyncio.run(scenario())


def test_billing_ui_is_not_presented_as_full_invoice_and_refresh_detects_transfer():
    for final in (False, True):
        text = "\n".join(servers._billing_lines({"active_seconds": 840, "estimated_cost_usd": 0.1031}, final=final))
        assert "$0.1031" in text
        assert "ليس إجمالي فاتورة Vast" in text
        assert "Download/Upload" in text
        assert "التكلفة النهائية المقدرة" not in text
    old = quote()
    new = replace(old, download_usd_per_gb=0)
    assert servers._offer_signature(old.public_dict()) != servers._offer_signature(new)
    assert "تغيّرت الأسعار" in servers._refresh_note([old], [new])


@pytest.mark.parametrize("field,value", [
    ("vast_estimated_download_gb", -1), ("vast_estimated_download_gb", float("nan")),
    ("vast_cost_comparison_hours", 0), ("vast_cost_comparison_hours", float("inf")),
    ("vast_max_download_usd_per_tb", -1), ("vast_max_download_usd_per_tb", float("nan")),
])
def test_cost_configuration_rejects_invalid_numbers(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_cost_configuration_defaults_and_explicit_free_only():
    settings = Settings(_env_file=None)
    assert settings.vast_max_download_usd_per_tb is None
    assert settings.vast_estimated_download_gb == 70
    assert settings.vast_cost_comparison_hours == 1
    assert Settings(_env_file=None, vast_max_download_usd_per_tb=0).vast_max_download_usd_per_tb == 0
