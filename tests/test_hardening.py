"""Regression tests for failures that happy-path and GPU-free mocks miss."""
import asyncio
import io
import threading
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from pixelpilot.config import Settings
from pixelpilot.contracts import (
    BoundedBuffer, MAX_HISTORY_CHARS, telegram_chunks, trim_history, visible_reply,
)
from pixelpilot.db import Database
from pixelpilot.domain import GpuOffer, InstanceRef
from pixelpilot.services.inference_client import InferenceClient
from pixelpilot.services.offer_policy import violations
from pixelpilot.services.orchestrator import Orchestrator, OrchestratorError
from pixelpilot.services.vast_gateway import normalize_offer
from pixelpilot.services.worker_safety import AuthenticatedBodyLimit, run_thread_safely


def quote(**overrides):
    fields = dict(offer_id=1, gpu_name="A6000", gpu_ram_gb=48, price_per_hour=.59,
                  reliability=.99, dlperf=60, verified=True, machine_id=101,
                  inet_down_mbps=650, inet_up_mbps=300, disk_space_gb=200,
                  num_gpus=1, direct_port_count=2, cpu_ram_gb=64,
                  download_usd_per_gb=0, upload_usd_per_gb=0)
    fields.update(overrides)
    return GpuOffer(**fields)


async def controller(tmp_path, inference, vast=None):
    settings = Settings(_env_file=None, database_path=tmp_path / "state.sqlite3",
                        pixelpilot_repo_url="https://example.invalid/repo")
    db = Database(settings.database_path)
    await db.init()
    await db.set_many({"instance.id": 7, "instance.phase": "ready",
                       "inference.url": "http://example.invalid", "inference.token": "test"})
    return Orchestrator(settings, db, vast, inference_factory=lambda *_: inference), db


def test_history_remains_bounded_after_many_long_turns():
    history = []
    for _ in range(100):
        history.extend([{"role": "user", "content": "س" * 4000},
                        {"role": "assistant", "content": "ج" * 4000}])
        history = trim_history(history, max_turns=10)
        assert sum(len(x["content"]) for x in history) <= MAX_HISTORY_CHARS
        assert len(history) % 2 == 0
        assert [x["role"] for x in history] == ["user", "assistant"] * (len(history) // 2)
    assert len(history) == 4


def test_history_discards_corrupt_and_incomplete_turns():
    assert trim_history(None) == []
    assert trim_history([{"role": "user", "content": "unfinished"}]) == []
    rows = [{"role": "user", "content": "old"}, None,
            {"role": "assistant", "content": "orphan"},
            {"role": "user", "content": "new", "image": "must-not-persist"},
            {"role": "assistant", "content": "answer"}]
    assert trim_history(rows) == [{"role": "user", "content": "new"},
                                  {"role": "assistant", "content": "answer"}]


@pytest.mark.parametrize("text,expected", [
    ("<think>unfinished private text", ""),
    ("<think>hidden</think>answer", "answer"),
    ("prefilled reasoning</think>answer", "answer"),
    ("answer <think>unclosed", "answer"),
])
def test_no_partial_thinking_leaks(text, expected):
    assert visible_reply(text) == expected


def test_emoji_chunks_fit_and_reconstruct_original():
    value = "😀" * 4500 + "<b>ليس HTML</b>"
    chunks = telegram_chunks(value)
    assert "".join(chunks) == value
    assert all(len(x.encode("utf-16-le")) // 2 <= 3500 for x in chunks)


def test_buffer_rejects_during_download_without_trusting_metadata():
    stream = BoundedBuffer(5)
    stream.write(b"12345")
    with pytest.raises(ValueError):
        stream.write(b"6")
    assert stream.getvalue() == b"12345"


@pytest.mark.parametrize("value", ["false", "0", False, "unverified"])
def test_verified_string_false_is_not_truthy(value):
    offer = normalize_offer({"id": 1, "verified": value, "dph_total": .5})
    assert offer.verified is False


@pytest.mark.parametrize("value", [None, "nan", "inf", float("nan"), -1, True])
def test_invalid_total_never_falls_back_to_cheaper_base(value):
    offer = normalize_offer({"id": 1, "dph_total": value, "dph_base": .1})
    assert offer.price_per_hour == 0
    assert "hourly_price" in violations(offer, Settings(_env_file=None))


@pytest.mark.parametrize("field,value,reason", [
    ("price_per_hour", .60001, "hourly_price"),
    ("num_gpus", None, "gpu_count"),
    ("direct_port_count", None, "direct_ports"),
    ("disk_space_gb", 50, "disk_space"),
    ("inet_up_mbps", 10, "upload_speed"),
    ("verified", None, "verification"),
])
def test_discovery_and_rental_use_the_same_strict_policy(field, value, reason):
    assert reason in violations(quote(**{field: value}), Settings(_env_file=None))


def test_offload_requires_known_sufficient_host_ram():
    assert "offload_ram" in violations(quote(gpu_ram_gb=24, cpu_ram_gb=None), Settings(_env_file=None))
    assert violations(quote(gpu_ram_gb=80), Settings(_env_file=None)) == []


def test_config_mutation_cannot_lift_the_hourly_cap():
    settings = Settings(_env_file=None)
    with pytest.raises(ValidationError):
        settings.vast_max_price_usd_hour = .61
    with pytest.raises(ValidationError):
        Settings(_env_file=None, inference_probe_timeout_seconds=float("nan"))
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chat_max_new_tokens=1)


def test_market_search_includes_performance_order_not_just_cheapest(tmp_path):
    class Vast:
        def __init__(self):
            self.orders = []
        async def search_offers(self, query, limit, *, order, **kwargs):
            self.orders.append(order)
            return [quote(gpu_ram_gb=80)] if order == "dlperf-" else []
    async def scenario():
        db = Database(tmp_path / "offers.sqlite3")
        await db.init()
        vast = Vast()
        orch = Orchestrator(Settings(_env_file=None), db, vast)
        offers = await orch.offers()
        assert offers and offers[0].gpu_ram_gb == 80
        assert set(vast.orders) == {"dph_total", "dlperf-", "inet_down-"}
    asyncio.run(scenario())


def test_metric_fluctuation_is_not_a_price_change():
    old = quote()
    new = replace(old, inet_down_mbps=601, inet_up_mbps=290, reliability=.991, dlperf=59)
    assert not Orchestrator._offer_snapshot_changed(old, new)
    assert violations(new, Settings(_env_file=None)) == []
    assert Orchestrator._offer_snapshot_changed(old, replace(new, price_per_hour=.58))
    assert Orchestrator._offer_snapshot_changed(old, replace(new, machine_id=102))


def test_chat_and_images_share_one_busy_gate(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Inference:
            async def chat(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return "answer"
        orch, db = await controller(tmp_path, Inference())
        task = asyncio.create_task(orch.chat("hello"))
        await entered.wait()
        with pytest.raises(OrchestratorError, match="قيد التنفيذ"):
            await orch.generate_image("draw", width=1024, height=1024, steps=20)
        assert await db.get("inference.active") is True
        release.set()
        await task
        assert await db.get("inference.active") is False
    asyncio.run(scenario())


def test_conversation_scopes_and_long_history_are_isolated(tmp_path):
    class Inference:
        async def chat(self, prompt, *, history, **kwargs):
            assert sum(len(x["content"]) for x in history) <= MAX_HISTORY_CHARS
            return "r" * 4000
    async def scenario():
        orch, db = await controller(tmp_path, Inference())
        for _ in range(12):
            await orch.chat("q" * 4000, history_key="chat.history:1")
        assert await db.get("chat.history:2", []) == []
        await orch.clear_chat_history(history_key="chat.history:1")
        assert await db.get("chat.history:1") == []
    asyncio.run(scenario())


def test_clear_waits_for_inflight_reply_and_does_not_resurrect_history(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Inference:
            async def chat(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return "answer"
        orch, db = await controller(tmp_path, Inference())
        task = asyncio.create_task(orch.chat("question"))
        await entered.wait()
        clear = asyncio.create_task(orch.clear_chat_history())
        await asyncio.sleep(0)
        assert not clear.done()
        release.set()
        await asyncio.gather(task, clear)
        assert await db.get("chat.history") == []
    asyncio.run(scenario())


def test_automatic_cleanup_rechecks_worker_busy_and_activity(tmp_path):
    class Inference:
        busy = True
        async def health_info(self):
            return {"busy": self.busy}
    class Vast:
        destroyed = []
        async def destroy_instance(self, instance_id):
            self.destroyed.append(instance_id)
    async def scenario():
        inf, vast = Inference(), Vast()
        orch, db = await controller(tmp_path, inf, vast)
        await db.set("instance.last_activity_at", "new")
        assert not await orch.destroy_current(expected_instance_id=7, expected_activity_at="old", only_if_idle=True)
        assert not await orch.destroy_current(expected_instance_id=7, expected_activity_at="new", only_if_idle=True)
        assert vast.destroyed == []
        inf.busy = False
        assert await orch.destroy_current(expected_instance_id=7, expected_activity_at="new", only_if_idle=True)
        assert vast.destroyed == [7]
    asyncio.run(scenario())


def test_cancelling_gpu_request_does_not_release_lock_before_thread_finishes():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        lock = asyncio.Lock()
        def work():
            entered.set()
            assert release.wait(2)
        async def operation():
            async with lock:
                await run_thread_safely(work)
        task = asyncio.create_task(operation())
        while not entered.is_set():
            await asyncio.sleep(.001)
        task.cancel()
        await asyncio.sleep(.01)
        task.cancel()  # repeated cancellation is safe too
        await asyncio.sleep(.01)
        assert lock.locked() and not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not lock.locked()
    asyncio.run(scenario())


def test_authentication_happens_before_receiving_any_body():
    async def scenario():
        sent = []
        async def forbidden(*args):
            raise AssertionError("unauthenticated body must not be read or parsed")
        async def send(event):
            sent.append(event)
        guard = AuthenticatedBodyLimit(forbidden, token=lambda: "secret", max_bytes=10)
        await guard({"type": "http", "headers": []}, forbidden, send)
        assert sent[0]["status"] == 401
    asyncio.run(scenario())


def test_chunked_body_cannot_bypass_limit():
    async def scenario():
        events = iter([{"type": "http.request", "body": b"1234", "more_body": True},
                       {"type": "http.request", "body": b"5678", "more_body": False}])
        sent = []
        async def receive():
            return next(events)
        async def send(event):
            sent.append(event)
        async def forbidden(*args):
            raise AssertionError("oversized body reached application")
        guard = AuthenticatedBodyLimit(forbidden, token=lambda: "secret", max_bytes=5)
        await guard({"type": "http", "headers": [(b"authorization", b"Bearer secret")]}, receive, send)
        assert sent[0]["status"] == 413
    asyncio.run(scenario())


def test_gateway_validation_does_not_echo_private_input(monkeypatch):
    from pixelpilot import inference_gateway as gateway
    monkeypatch.setattr(gateway, "TOKEN", "secret")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app), base_url="http://worker") as client:
            reply = await client.post("/v1/chat/completions", headers={"Authorization": "Bearer secret"},
                                      json={"prompt": "private-medical-text", "images": ["private"] * 4})
            assert reply.status_code == 422
            assert "private" not in reply.text
    asyncio.run(scenario())


def test_image_orientation_is_normalized_before_vision_and_editing():
    from pixelpilot import inference_gateway as gateway
    image = Image.new("RGB", (20, 10))
    exif = Image.Exif()
    exif[274] = 6
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    assert gateway._decode_uploaded_image(buffer.getvalue()).size == (10, 20)


def test_pixel_budget_is_checked_before_image_load(monkeypatch):
    from pixelpilot import inference_gateway as gateway
    from fastapi import HTTPException
    class HugeImage:
        width, height = 10_000, 10_000
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def load(self):
            raise AssertionError("pixels were decoded before validation")
    monkeypatch.setattr(Image, "open", lambda *_: HugeImage())
    with pytest.raises(HTTPException) as error:
        gateway._decode_uploaded_image(b"not-empty")
    assert error.value.status_code == 413


def test_switching_is_busy_not_an_unhealthy_runtime(monkeypatch):
    from pixelpilot import inference_gateway as gateway
    monkeypatch.setattr(gateway, "TOKEN", "test")
    monkeypatch.setattr(gateway, "state", gateway.RuntimeState(initialized=True, active_model="loading-image"))
    assert asyncio.run(gateway.health("Bearer test"))["status"] == "ok"
    assert len(asyncio.run(gateway.models("Bearer test"))["data"]) == 2


def test_legacy_worker_is_not_announced_ready_for_multimodal_chat():
    class Client(InferenceClient):
        async def health_info(self):
            return {"status": "ok"}
        async def models(self):
            return ["image", "chat"]
    client = Client("http://test", "token", "image", chat_model_id="chat")
    assert asyncio.run(client.is_ready()) is False


@pytest.mark.parametrize("action", ["start_instance", "stop_instance", "destroy_instance"])
@pytest.mark.parametrize("result", [{"success": False}, {"success": "false"}, {}, None])
def test_unconfirmed_lifecycle_is_never_reported_as_success(action, result):
    from pixelpilot.services.vast_gateway import VastError, VastSdkGateway
    async def scenario():
        gateway = VastSdkGateway("fake")
        gateway._client = SimpleNamespace(**{action: lambda **_: result})
        with pytest.raises(VastError, match="not confirmed"):
            await getattr(gateway, action)(7)
    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["start_instance", "stop_instance", "destroy_instance"])
def test_confirmed_lifecycle_acknowledgement(action):
    from pixelpilot.services.vast_gateway import VastSdkGateway
    async def scenario():
        gateway = VastSdkGateway("fake")
        gateway._client = SimpleNamespace(**{action: lambda **_: {"success": True}})
        await getattr(gateway, action)(7)
    asyncio.run(scenario())


def test_failed_destruction_keeps_instance_and_billing_tracking(tmp_path):
    from pixelpilot.services.vast_gateway import VastError
    class Vast:
        async def destroy_instance(self, instance_id):
            raise VastError("rejected")
    async def scenario():
        orch, db = await controller(tmp_path, None, Vast())
        await db.set("billing.price_per_hour", .59)
        with pytest.raises(VastError):
            await orch.destroy_current()
        assert await db.get("instance.id") == 7
        assert await db.get("billing.price_per_hour") == .59
    asyncio.run(scenario())


@pytest.mark.parametrize("override", [
    {"prompt": "x" * 12001}, {"negative_prompt": "x" * 12001},
    {"true_cfg_scale": float("nan")}, {"true_cfg_scale": 21.0},
])
def test_image_edit_parameters_are_validated_before_model_loading(override):
    from pixelpilot import inference_gateway as gateway
    from fastapi import HTTPException
    values = dict(prompt="draw", width=1024, height=1024, steps=20, seed=1,
                  reference_images=[], true_cfg_scale=1.0, negative_prompt=None,
                  enhance_prompt=False)
    values.update(override)
    with pytest.raises(HTTPException) as error:
        asyncio.run(gateway._generate_response(**values))
    assert error.value.status_code == 422
