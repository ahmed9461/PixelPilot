import asyncio
from types import SimpleNamespace

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import InstanceRef
from pixelpilot.services.orchestrator import Orchestrator

from pixelpilot.bot.routers import servers


def test_lifecycle_task_can_be_cancelled_cleanly():
    async def scenario():
        gate = asyncio.Event()

        async def worker():
            await gate.wait()

        servers._track_lifecycle(worker(), name="test-server-lifecycle")
        assert servers._lifecycle_busy() is True
        await servers._cancel_lifecycle_if_running()
        assert servers._lifecycle_busy() is False

    asyncio.run(scenario())


def test_status_labels_cover_renting_and_provisioning():
    assert "الاستئجار" in servers._status_label({"phase": "renting"})
    assert "التجهيز" in servers._status_label({"phase": "provisioning"})


def test_ready_status_detects_unready_inference():
    assert "غير جاهز" in servers._status_label(
        {"phase": "ready", "inference_ready": False}
    )


def test_rapid_rent_taps_reserve_one_background_slot(monkeypatch):
    async def scenario():
        gate = asyncio.Event()
        starts = 0
        answers = []

        async def fake_rent(callback, offer_id, preferred_only):
            nonlocal starts
            starts += 1
            await gate.wait()

        async def fake_answer(callback, *args, **kwargs):
            answers.append(args)

        class Callback:
            data = "servers:rent:78"

        monkeypatch.setattr(servers, "_rent_from_callback", fake_rent)
        monkeypatch.setattr(servers, "safe_callback_answer", fake_answer)
        try:
            await asyncio.gather(servers.rent(Callback()), servers.rent(Callback()))
            await asyncio.sleep(0)
            assert starts == 1
            assert len(answers) == 1
        finally:
            gate.set()
            if servers._lifecycle_task:
                await servers._lifecycle_task

    asyncio.run(scenario())


def test_manual_stop_waits_for_inflight_start_mutation(tmp_path):
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        class Vast:
            async def start_instance(self, instance_id):
                calls.append("start-begun")
                started.set()
                await release.wait()
                calls.append("start-finished")

            async def stop_instance(self, instance_id):
                calls.append("stop")

        class Inference:
            async def is_ready(self):
                await asyncio.sleep(10)

        settings = Settings(_env_file=None, database_path=tmp_path / "db.sqlite3")
        db = Database(settings.database_path)
        await db.init()
        await db.set("instance.id", 123)
        await db.set("instance.phase", "stopped")
        orchestrator = Orchestrator(settings, db, Vast(),
                                    inference_factory=lambda url, token: Inference())
        servers.configure(orchestrator)
        servers._track_lifecycle(orchestrator.start_current(), name="slow-start")
        await started.wait()
        callback = SimpleNamespace(message=SimpleNamespace(edit_text=None))
        manual = asyncio.create_task(servers._prepare_manual_control(callback))
        await asyncio.sleep(0.01)
        assert calls == ["start-begun"]
        release.set()
        assert await manual is True
        assert await orchestrator.stop_current() is True
        assert calls == ["start-begun", "start-finished", "stop"]

    asyncio.run(scenario())
