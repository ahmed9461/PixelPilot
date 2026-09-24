import asyncio

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GeneratedImage, GpuOffer, InstanceRef, ReferenceImage
from pixelpilot.services.orchestrator import Orchestrator, _extract_instance_id


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
