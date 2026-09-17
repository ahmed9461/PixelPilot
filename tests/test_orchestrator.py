import asyncio

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GpuOffer, InferenceResult, InstanceRef
from pixelpilot.services.orchestrator import Orchestrator, _extract_instance_id


def test_extract_instance_id_direct():
    assert _extract_instance_id({"instance_id": 123}) == 123


def test_extract_instance_id_nested():
    assert _extract_instance_id({"new_contract": {"id": 456}}) == 456


def test_extract_instance_id_missing():
    assert _extract_instance_id({"ok": True}) is None


class FakeVast:
    def __init__(self):
        self.destroyed = []; self.stopped = []; self.started = []; self.create_kwargs = None
    async def search_offers(self, query, limit):
        return [GpuOffer(offer_id=77, gpu_name="H100", gpu_ram_gb=80, price_per_hour=1.5, reliability=0.99, dlperf=80)]
    async def create_instance(self, offer_id, **kwargs):
        self.create_kwargs = kwargs; return {"success": True, "new_contract": 321}
    async def find_instances_by_label(self, label, limit=5):
        return []
    async def show_instance(self, instance_id):
        return InstanceRef(instance_id=instance_id, status="running", public_ip="203.0.113.5", mapped_port=45678)
    async def destroy_instance(self, instance_id): self.destroyed.append(instance_id)
    async def stop_instance(self, instance_id): self.stopped.append(instance_id)
    async def start_instance(self, instance_id): self.started.append(instance_id)


class FakeInference:
    def __init__(self): self.messages = None
    async def is_ready(self): return True
    async def chat(self, messages, max_tokens):
        self.messages = messages
        return InferenceResult(text="أهلًا بك", model="Qwen/Qwen3-Omni-30B-A3B-Instruct")


def test_orchestrator_full_fake_lifecycle(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1, vast_api_key="v", pixelpilot_repo_url="https://example.invalid/PixelPilot.git", database_path=tmp_path / "db.sqlite3", provision_poll_seconds=0.001, inference_ready_timeout_seconds=1, inference_request_timeout_seconds=1)
        db = Database(settings.database_path); await db.init()
        vast = FakeVast(); inference = FakeInference()
        orch = Orchestrator(settings, db, vast, inference_factory=lambda url, token: inference)
        offers = await orch.offers(); assert offers[0].offer_id == 77
        await orch.rent_and_prepare(77)
        assert await db.get("instance.phase") == "ready"
        assert "PIXELPILOT_INFERENCE_TOKEN" in vast.create_kwargs["env"]
        assert "MODEL_ID=Qwen/Qwen3-Omni-30B-A3B-Instruct" in vast.create_kwargs["env"]
        assert "COMFY" not in vast.create_kwargs["env"]
        messages = [{"role": "user", "content": "مرحبا"}]
        result = await orch.chat(messages)
        assert result.text == "أهلًا بك" and inference.messages == messages
        assert all(item.get("role") != "system" for item in inference.messages)
        assert await orch.stop_current() is True and vast.stopped == [321]
        assert await orch.start_current() is True and vast.started == [321]
        assert await orch.destroy_current() is True and vast.destroyed == [321]
        assert await db.get("instance.id") is None
    asyncio.run(scenario())


def test_recover_exited_marks_error(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1, vast_api_key="v", pixelpilot_repo_url="https://example.invalid/PixelPilot.git", database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path); await db.init(); await db.set("instance.id", 888)
        class ExitedVast(FakeVast):
            async def show_instance(self, instance_id): return InstanceRef(instance_id=instance_id, status="exited")
        orch = Orchestrator(settings, db, ExitedVast(), inference_factory=lambda url, token: FakeInference())
        await orch.recover_current(); assert await db.get("instance.phase") == "error"
    asyncio.run(scenario())


def test_rent_recovers_instance_after_ambiguous_create_failure(tmp_path):
    async def scenario():
        settings = Settings(_env_file=None, telegram_bot_token="t", owner_telegram_id=1, vast_api_key="v", pixelpilot_repo_url="https://example.invalid/PixelPilot.git", database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path); await db.init()
        class AmbiguousVast(FakeVast):
            async def create_instance(self, offer_id, **kwargs): self.create_kwargs = kwargs; raise TimeoutError("connection dropped after request")
            async def find_instances_by_label(self, label, limit=5): return [InstanceRef(instance_id=654, status="loading")]
        vast = AmbiguousVast(); orch = Orchestrator(settings, db, vast, inference_factory=lambda url, token: FakeInference())
        await orch.offers(); result = await orch.rent(77)
        assert result["instance_id"] == 654 and await db.get("instance.id") == 654
        assert await db.get("instance.pending_label") is None
    asyncio.run(scenario())
