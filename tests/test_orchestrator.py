import asyncio

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GenerationSpec, InstanceRef
from pixelpilot.services.orchestrator import Orchestrator, _extract_instance_id


def test_extract_instance_id_direct():
    assert _extract_instance_id({"instance_id": 123}) == 123


def test_extract_instance_id_nested():
    assert _extract_instance_id({"new_contract": {"id": 456}}) == 456


def test_extract_instance_id_missing():
    assert _extract_instance_id({"ok": True}) is None


class FakeVast:
    def __init__(self):
        self.destroyed = []
        self.stopped = []
        self.started = []
        self.create_kwargs = None

    async def search_offers(self, query, limit):
        from pixelpilot.domain import GpuOffer
        return [GpuOffer(offer_id=77, gpu_name="A6000", gpu_ram_gb=48, price_per_hour=0.4, reliability=0.99, dlperf=20)]

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


class FakeWorker:
    async def is_ready(self):
        return True

    async def submit(self, spec, filename_prefix):
        return "prompt-1"

    async def wait_job(self, prompt_id, timeout_seconds):
        return {"status": "completed", "images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}

    async def download_image(self, image):
        return b"PNGDATA"


def test_orchestrator_full_fake_lifecycle(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            hf_token="hf_readonly",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            provision_poll_seconds=0.001,
            provision_ready_timeout_seconds=1,
            worker_generation_timeout_seconds=1,
        )
        db = Database(settings.database_path)
        await db.init()
        vast = FakeVast()
        worker = FakeWorker()
        orch = Orchestrator(settings, db, vast, worker_factory=lambda url, token: worker)

        offers = await orch.offers()
        assert offers[0].offer_id == 77
        await orch.rent_and_prepare(77)
        assert await db.get("instance.phase") == "ready"
        assert vast.create_kwargs["template_hash"] is None
        assert "OPEN_BUTTON_TOKEN" in vast.create_kwargs["env"]
        assert "HF_TOKEN" in vast.create_kwargs["env"]
        assert "bootstrap_vast.sh" in vast.create_kwargs["onstart_cmd"]

        spec = GenerationSpec(prompt="natural photo", seed=42)
        result = await orch.generate(spec)
        assert result.generation_id == 1
        assert result.images[0].filename == "x.png"
        content, image = await orch.download_generation_image(result.generation_id, 0)
        assert content == b"PNGDATA"
        assert image.filename == "x.png"

        assert await orch.stop_current() is True
        assert vast.stopped == [321]
        assert await orch.start_current() is True
        assert vast.started == [321]
        assert await orch.destroy_current() is True
        assert vast.destroyed == [321]
        assert await db.get("instance.id") is None

    asyncio.run(scenario())


def test_recover_exited_marks_error(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            hf_token="hf_readonly",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 888)

        class ExitedVast(FakeVast):
            async def show_instance(self, instance_id):
                return InstanceRef(instance_id=instance_id, status="exited")

        orch = Orchestrator(settings, db, ExitedVast(), worker_factory=lambda url, token: FakeWorker())
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
            hf_token="hf_readonly",
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
        orch = Orchestrator(settings, db, vast, worker_factory=lambda url, token: FakeWorker())
        await orch.offers()
        result = await orch.rent(77)
        assert result["instance_id"] == 654
        assert await db.get("instance.id") == 654
        assert await db.get("instance.pending_label") is None
        assert vast.create_kwargs["label"].startswith("PixelPilot-")

    asyncio.run(scenario())


def test_recover_pending_rent_by_unique_label(tmp_path):
    async def scenario():
        settings = Settings(
            _env_file=None,
            telegram_bot_token="t",
            owner_telegram_id=1,
            vast_api_key="v",
            hf_token="hf_readonly",
            pixelpilot_repo_url="https://example.invalid/PixelPilot.git",
            database_path=tmp_path / "db.sqlite3",
            provision_poll_seconds=0.001,
            provision_ready_timeout_seconds=1,
        )
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.pending_label", "PixelPilot-pending")
        await db.set("worker.token", "worker-secret")

        class PendingVast(FakeVast):
            async def find_instances_by_label(self, label, limit=5):
                assert label == "PixelPilot-pending"
                return [InstanceRef(instance_id=777, status="running", public_ip="203.0.113.7", mapped_port=40000)]

        orch = Orchestrator(settings, db, PendingVast(), worker_factory=lambda url, token: FakeWorker())
        await orch.recover_current()
        assert await db.get("instance.id") == 777
        assert await db.get("instance.pending_label") is None
        assert await db.get("instance.phase") == "ready"

    asyncio.run(scenario())
