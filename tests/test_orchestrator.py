import asyncio

import pytest

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GeneratedImage, GpuOffer, InstanceRef, ReferenceImage
from pixelpilot.services.vast_gateway import VastCreateRejected
from pixelpilot.services.orchestrator import (
    OfferChangedError,
    OfferUnavailableError,
    Orchestrator,
    OrchestratorError,
    RentRejectedError,
    _extract_instance_id,
)


def test_extract_instance_id_direct():
    assert _extract_instance_id({"instance_id": 123}) == 123


def test_extract_instance_id_nested():
    assert _extract_instance_id({"new_contract": {"id": 456}}) == 456


class FakeVast:
    def __init__(self):
        self.destroyed = []
        self.stopped = []
        self.started = []
        self.create_kwargs = None
        self.search_calls = []

    async def search_offers(self, query, limit, **kwargs):
        self.search_calls.append((query, limit, kwargs))
        preferred = GpuOffer(78, "RTX A6000", 48, 0.40, 0.99, 40)
        if "gpu_ram>=48" in query:
            return [preferred]
        return [
            GpuOffer(77, "RTX 4090", 24, 0.25, 0.99, 60),
            preferred,
        ]

    async def lookup_offer(self, offer_id, *, storage_gb):
        rows = await self.search_offers(f"id={offer_id} rentable=true", 1, storage_gb=storage_gb)
        return next((row for row in rows if row.offer_id == offer_id), None)

    async def create_instance(self, offer_id, **kwargs):
        self.create_kwargs = kwargs
        return {"success": True, "new_contract": 321}

    async def find_instances_by_label(self, label, limit=5):
        return []

    async def show_instance(self, instance_id):
        return InstanceRef(instance_id=instance_id, status="running", public_ip="203.0.113.5", mapped_port=45678)

    async def destroy_instance(self, instance_id):
        self.destroyed.append(instance_id)

    async def stop_instance(self, instance_id):
        self.stopped.append(instance_id)

    async def start_instance(self, instance_id):
        self.started.append(instance_id)


class FakeInference:
    def __init__(self):
        self.request = None

    async def is_ready(self):
        return True

    async def generate(self, prompt, **kwargs):
        self.request = (prompt, kwargs)
        return GeneratedImage(
            data=b"png",
            mime_type="image/png",
            seed=123,
            width=kwargs["width"],
            height=kwargs["height"],
            model="Qwen/Qwen-Image-2.1",
            reference_count=len(kwargs.get("reference_images") or ()),
        )


def test_orchestrator_full_fake_lifecycle(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            provision_poll_seconds=0.001,
            inference_ready_timeout_seconds=1,
            inference_request_timeout_seconds=1,
        )
        db = Database(settings.database_path)
        await db.init()
        vast = FakeVast()
        inference = FakeInference()
        orch = Orchestrator(settings, db, vast, inference_factory=lambda url, token: inference)

        offers = await orch.offers()
        assert offers[0].gpu_ram_gb == 48
        assert len(vast.search_calls) == 2
        assert "gpu_ram>=48" in vast.search_calls[0][0]
        assert "gpu_ram>=24" in vast.search_calls[1][0]
        assert vast.search_calls[0][1] == settings.vast_search_pool_limit
        await orch.rent_and_prepare(78)
        assert await db.get("instance.phase") == "ready"
        env = vast.create_kwargs["env"]
        assert "MODEL_ID=Qwen/Qwen-Image-2.1" in env
        assert "IMAGE_MEMORY_MODE=auto" in env
        assert "IMAGE_MAX_REFERENCE_IMAGES=10" in env
        assert "PROMPT_ENHANCER_T2I_ID=Qwen/Qwen-Image-2.1-PE-T2I" in env
        assert "PROMPT_ENHANCER_I2I_ID=Qwen/Qwen-Image-2.1-PE-I2I" in env
        assert "WHISPER" not in env
        assert "VLLM" not in env

        prompt = "  نفس البرومت كما هو  "
        result = await orch.generate_image(
            prompt,
            width=1024,
            height=1024,
            steps=40,
            reference_images=(ReferenceImage(b"x"),),
            enhance_prompt=True,
        )
        assert result.data == b"png"
        assert inference.request[0] == prompt
        assert inference.request[1]["enhance_prompt"] is True

        assert await orch.stop_current() is True
        assert await orch.start_current() is True
        assert await orch.destroy_current() is True
        assert await db.get("instance.id") is None

    asyncio.run(scenario())


def test_recover_exited_marks_error(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 888)

        class ExitedVast(FakeVast):
            async def show_instance(self, instance_id):
                return InstanceRef(instance_id=instance_id, status="exited")

        orch = Orchestrator(settings, db, ExitedVast(), inference_factory=lambda url, token: FakeInference())
        await orch.recover_current()
        assert await db.get("instance.phase") == "error"

    asyncio.run(scenario())


def test_rent_recovers_instance_after_ambiguous_create_failure(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()

        class AmbiguousVast(FakeVast):
            async def create_instance(self, offer_id, **kwargs):
                self.create_kwargs = kwargs
                raise TimeoutError("connection dropped after request")

            async def find_instances_by_label(self, label, limit=5):
                return [InstanceRef(instance_id=654, status="loading")]

        vast = AmbiguousVast()
        orch = Orchestrator(settings, db, vast, inference_factory=lambda url, token: FakeInference())
        await orch.offers()
        result = await orch.rent(78)
        assert result["instance_id"] == 654
        assert await db.get("instance.id") == 654

    asyncio.run(scenario())



def test_preferred_only_offer_search_skips_fallback_pool(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()
        vast = FakeVast()
        orch = Orchestrator(
            settings,
            db,
            vast,
            inference_factory=lambda url, token: FakeInference(),
        )

        offers = await orch.offers(preferred_only=True)
        assert len(vast.search_calls) == 1
        assert "gpu_ram>=48" in vast.search_calls[0][0]
        assert offers
        assert all(item.gpu_ram_gb >= 48 for item in offers)
        assert await db.get("offers.search_mode") == "preferred"

    asyncio.run(scenario())



def test_readiness_probe_times_out_without_blocking(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            inference_probe_timeout_seconds=0.01,
        )
        db = Database(settings.database_path)
        await db.init()
        orch = Orchestrator(
            settings,
            db,
            FakeVast(),
            inference_factory=lambda url, token: FakeInference(),
        )

        class SlowInference:
            async def is_ready(self):
                await asyncio.sleep(1)
                return True

        started = asyncio.get_running_loop().time()
        ready = await orch._probe_inference_ready(SlowInference())
        elapsed = asyncio.get_running_loop().time() - started
        assert ready is False
        assert elapsed < 0.2

    asyncio.run(scenario())


def test_vast_status_read_is_bounded(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            vast_status_timeout_seconds=0.01,
        )
        db = Database(settings.database_path)
        await db.init()

        class SlowVast(FakeVast):
            async def show_instance(self, instance_id):
                await asyncio.sleep(1)
                return InstanceRef(instance_id=instance_id, status="running")

        orch = Orchestrator(
            settings,
            db,
            SlowVast(),
            inference_factory=lambda url, token: FakeInference(),
        )
        started = asyncio.get_running_loop().time()
        try:
            await orch._show_instance_bounded(1)
        except OrchestratorError:
            pass
        else:
            raise AssertionError("expected bounded Vast status timeout")
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 0.2

    asyncio.run(scenario())


def test_timed_out_status_does_not_spawn_overlapping_sdk_reads(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, database_path=tmp_path / "db.sqlite3",
                            vast_status_timeout_seconds=0.01)
        db = Database(settings.database_path)

        class SlowVast(FakeVast):
            def __init__(self):
                super().__init__()
                self.calls = 0
                self.release = asyncio.Event()

            async def show_instance(self, instance_id):
                self.calls += 1
                await self.release.wait()
                return InstanceRef(instance_id=instance_id, status="running")

        vast = SlowVast()
        orch = Orchestrator(settings, db, vast)
        for _ in range(3):
            with pytest.raises(OrchestratorError):
                await orch._show_instance_bounded(1)
        assert vast.calls == 1
        vast.release.set()
        await orch._show_instance_bounded(1)

    asyncio.run(scenario())


def test_wait_until_ready_preserves_stopped_state(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            provision_poll_seconds=0.01,
            inference_ready_timeout_seconds=1,
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 55)
        await db.set("instance.phase", "provisioning")

        class StoppedVast(FakeVast):
            async def show_instance(self, instance_id):
                return InstanceRef(instance_id=instance_id, status="stopped")

        orch = Orchestrator(
            settings,
            db,
            StoppedVast(),
            inference_factory=lambda url, token: FakeInference(),
        )
        try:
            await orch.wait_until_ready(55)
        except OrchestratorError:
            pass
        else:
            raise AssertionError("expected stopped provisioning to end")
        assert await db.get("instance.phase") == "stopped"

    asyncio.run(scenario())


def test_offer_search_hides_rows_above_final_price_ceiling(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            vast_max_price_usd_hour=0.50,
        )
        db = Database(settings.database_path)
        await db.init()

        class PriceVast(FakeVast):
            async def search_offers(self, query, limit, **kwargs):
                if "gpu_ram>=48" in query:
                    return [
                        GpuOffer(1, "RTX A6000", 48, 0.49, 0.99, 40),
                        GpuOffer(2, "RTX A6000", 48, 0.53, 0.99, 42),
                    ]
                return [
                    GpuOffer(3, "RTX 3090", 24, 0.25, 0.99, 60),
                ]

        orch = Orchestrator(
            settings,
            db,
            PriceVast(),
            inference_factory=lambda url, token: FakeInference(),
        )
        offers = await orch.offers()
        assert [item.offer_id for item in offers] == [1, 3]
        assert all(item.price_per_hour <= 0.50 for item in offers)

    asyncio.run(scenario())



def test_current_state_reconciles_stopped_phase(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 101)
        await db.set("instance.phase", "ready")

        class StoppedVast(FakeVast):
            async def show_instance(self, instance_id):
                return InstanceRef(instance_id=instance_id, status="stopped")

        orch = Orchestrator(
            settings,
            db,
            StoppedVast(),
            inference_factory=lambda url, token: FakeInference(),
        )
        state = await orch.current_state(probe_inference=False)
        assert state["phase"] == "stopped"
        assert await db.get("instance.phase") == "stopped"

    asyncio.run(scenario())


def test_current_state_reconciles_terminal_phase(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 102)
        await db.set("instance.phase", "ready")

        class DeadVast(FakeVast):
            async def show_instance(self, instance_id):
                return InstanceRef(instance_id=instance_id, status="exited")

        orch = Orchestrator(
            settings,
            db,
            DeadVast(),
            inference_factory=lambda url, token: FakeInference(),
        )
        state = await orch.current_state(probe_inference=False)
        assert state["phase"] == "error"
        assert await db.get("instance.phase") == "error"

    asyncio.run(scenario())



def test_rent_revalidates_exact_offer_and_rejects_stale_id(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()

        class StaleOfferVast(FakeVast):
            def __init__(self):
                super().__init__()
                self.live = True

            async def search_offers(self, query, limit, **kwargs):
                self.search_calls.append((query, limit, kwargs))
                if self.live:
                    preferred = GpuOffer(
                        78, "RTX A6000", 48, 0.40, 0.99, 40
                    )
                    if "gpu_ram>=48" in query:
                        return [preferred]
                    return [preferred]
                return []

        vast = StaleOfferVast()
        orch = Orchestrator(
            settings,
            db,
            vast,
            inference_factory=lambda url, token: FakeInference(),
        )
        await orch.offers()
        vast.live = False

        try:
            await orch.rent(78)
        except OfferUnavailableError as exc:
            assert "78" in str(exc)
        else:
            raise AssertionError("expected stale offer rejection")

        assert vast.create_kwargs is None
        assert await db.get("instance.id") is None

    asyncio.run(scenario())


def test_rent_requires_reconfirmation_when_price_changes(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()

        class ChangedOfferVast(FakeVast):
            def __init__(self):
                super().__init__()
                self.price = 0.40

            async def search_offers(self, query, limit, **kwargs):
                self.search_calls.append((query, limit, kwargs))
                offer = GpuOffer(
                    78, "RTX A6000", 48, self.price, 0.99, 40
                )
                return [offer]

        vast = ChangedOfferVast()
        orch = Orchestrator(
            settings,
            db,
            vast,
            inference_factory=lambda url, token: FakeInference(),
        )
        await orch.offers()
        vast.price = 0.45

        try:
            await orch.rent(78)
        except OfferChangedError as exc:
            assert "78" in str(exc)
        else:
            raise AssertionError("expected changed offer rejection")

        assert vast.create_kwargs is None

    asyncio.run(scenario())


def test_explicit_vast_rejection_clears_pending_rent_state(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()

        class RejectingVast(FakeVast):
            async def create_instance(self, offer_id, **kwargs):
                self.create_kwargs = kwargs
                raise VastCreateRejected("offer unavailable")

        vast = RejectingVast()
        orch = Orchestrator(
            settings,
            db,
            vast,
            inference_factory=lambda url, token: FakeInference(),
        )
        await orch.offers()

        try:
            await orch.rent(78)
        except RentRejectedError as exc:
            assert "offer unavailable" in str(exc)
        else:
            raise AssertionError("expected explicit rental rejection")

        assert await db.get("instance.phase") == "none"
        assert await db.get("instance.pending_label") is None
        assert await db.get("instance.offer") is None
        assert await db.get("inference.token") is None

    asyncio.run(scenario())


def test_rent_exact_id_survives_ranked_market_churn(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1,
                            vast_api_key="v", pixelpilot_repo_url="https://example.invalid/repo",
                            database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path)
        await db.init()

        class ChurnVast(FakeVast):
            async def lookup_offer(self, offer_id, *, storage_gb):
                # Search result has fallen outside the top 64, but the exact ID is live.
                assert offer_id == 78
                return GpuOffer(78, "RTX A6000", 48, 0.40, 0.99, 40)

        vast = ChurnVast()
        orch = Orchestrator(settings, db, vast)
        await orch.offers()
        assert (await orch.rent(78))["instance_id"] == 321
        assert vast.create_kwargs["cancel_unavail"] is True

    asyncio.run(scenario())


def test_ambiguous_timeout_blocks_another_paid_rent_until_recovery(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1,
                            vast_api_key="v", pixelpilot_repo_url="https://example.invalid/repo",
                            database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path)
        await db.init()

        class DelayedVast(FakeVast):
            def __init__(self):
                super().__init__()
                self.creates = 0
                self.instances = []

            async def create_instance(self, offer_id, **kwargs):
                self.creates += 1
                raise TimeoutError("request outcome unknown")

            async def find_instances_by_label(self, label, limit=5):
                return self.instances

        vast = DelayedVast()
        orch = Orchestrator(settings, db, vast)
        await orch.offers()
        try:
            await orch.rent(78)
        except OrchestratorError:
            pass
        else:
            raise AssertionError("expected ambiguous result")
        assert await db.get("instance.pending_label")
        try:
            await orch.rent(78)
        except OrchestratorError:
            pass
        else:
            raise AssertionError("pending rent must block a second create")
        assert vast.creates == 1
        vast.instances = [InstanceRef(instance_id=654, status="stopped")]
        assert await orch.reconcile_pending() == 654
        assert await db.get("instance.id") == 654
        assert await db.get("billing.price_per_hour") == 0.40

    asyncio.run(scenario())


def test_concurrent_rent_calls_create_only_one_instance(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1,
                            vast_api_key="v", pixelpilot_repo_url="https://example.invalid/repo",
                            database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path)
        await db.init()

        class SlowCreate(FakeVast):
            def __init__(self):
                super().__init__()
                self.creates = 0

            async def create_instance(self, offer_id, **kwargs):
                self.creates += 1
                await asyncio.sleep(0.01)
                return {"new_contract": 321}

        vast = SlowCreate()
        orch = Orchestrator(settings, db, vast)
        await orch.offers()
        results = await asyncio.gather(orch.rent(78), orch.rent(78), return_exceptions=True)
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, OrchestratorError) for result in results) == 1
        assert vast.creates == 1

    asyncio.run(scenario())


def test_single_status_timeout_is_retried_during_provisioning(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1,
                            vast_api_key="v", pixelpilot_repo_url="https://example.invalid/repo",
                            database_path=tmp_path / "db.sqlite3", vast_status_timeout_seconds=0.01,
                            provision_poll_seconds=0.001, inference_ready_timeout_seconds=1)
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 55)

        class SlowOnceVast(FakeVast):
            def __init__(self):
                super().__init__()
                self.probes = 0

            async def show_instance(self, instance_id):
                self.probes += 1
                if self.probes == 1:
                    await asyncio.sleep(0.1)
                return InstanceRef(instance_id=instance_id, status="running",
                                   public_ip="203.0.113.5", mapped_port=45678)

        vast = SlowOnceVast()
        orch = Orchestrator(settings, db, vast,
                            inference_factory=lambda url, token: FakeInference())
        await orch.wait_until_ready(55)
        assert vast.probes == 1  # the timed-out read completes without a duplicate SDK call
        assert await db.get("instance.phase") == "ready"

    asyncio.run(scenario())


def test_offer_queries_require_host_ram_only_for_offload(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "db.sqlite3")
    orch = Orchestrator(settings, Database(settings.database_path), FakeVast())
    assert "cpu_ram>=48" in orch._offer_query_for(24)
    assert "cpu_ram>=" not in orch._offer_query_for(48)


@pytest.mark.parametrize("changed", [
    GpuOffer(78, "Different GPU", 48, 0.40, 0.99, 40),
    GpuOffer(78, "RTX A6000", 47, 0.40, 0.99, 40),
    GpuOffer(78, "RTX A6000", 48, 0.51, 0.99, 40),
    GpuOffer(78, "RTX A6000", 48, 0.40, 0.99, 40, verified=False),
])
def test_rent_rejects_changed_gpu_vram_price_or_policy(tmp_path, changed):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1,
                            vast_api_key="v", pixelpilot_repo_url="https://example.invalid/repo",
                            database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path)
        await db.init()

        class ChangedVast(FakeVast):
            async def lookup_offer(self, offer_id, *, storage_gb):
                return changed

        vast = ChangedVast()
        orch = Orchestrator(settings, db, vast)
        await orch.offers()
        with pytest.raises(OfferChangedError):
            await orch.rent(78)
        assert vast.create_kwargs is None

    asyncio.run(scenario())
