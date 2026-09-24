import asyncio

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
