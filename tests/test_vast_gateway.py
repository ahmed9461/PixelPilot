from pixelpilot.services.vast_gateway import build_offer_query, extract_mapped_port, normalize_offer


def test_build_query_contains_cost_ram_and_safety_filters():
    q = build_offer_query(
        48,
        0.98,
        1.5,
        disk_gb=100,
        verified_only=True,
        min_direct_ports=2,
        min_inet_down_mbps=100,
    )
    assert "gpu_ram>=48" in q
    assert "gpu_ram>=48000" not in q
    assert "reliability>=0.9800" in q
    assert "dph_total<=1.5000" in q
    assert "num_gpus=1" in q
    assert "disk_space>=100" in q
    assert "verified=true" in q
    assert "direct_port_count>=2" in q
    assert "inet_down>=100" in q


def test_normalize_offer():
    offer = normalize_offer({
        "id": 77,
        "gpu_name": "RTX A6000",
        "gpu_ram": 49140,
        "dph_total": 0.42,
        "reliability": 0.995,
        "dlperf": 23.0,
        "inet_down": 750,
        "disk_space": 500,
        "verification": "verified",
    })
    assert offer.offer_id == 77
    assert offer.gpu_name == "RTX A6000"
    assert 49 <= offer.gpu_ram_gb <= 50
    assert offer.price_per_hour == 0.42
    assert offer.reliability == 0.995
    assert offer.inet_down_mbps == 750
    assert offer.verified is True


def test_extract_mapped_port_from_vast_raw():
    raw = {"public_ipaddr": "203.0.113.10", "ports": {"8190/tcp": [{"HostIp": "0.0.0.0", "HostPort": "34567"}]}}
    assert extract_mapped_port(raw, 8190) == 34567


def test_gateway_requests_raw_json_from_official_sdk(monkeypatch):
    import sys
    import types
    captured = {}
    class FakeVastAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "vastai", types.SimpleNamespace(VastAI=FakeVastAI))
    from pixelpilot.services.vast_gateway import VastSdkGateway
    gateway = VastSdkGateway("secret")
    gateway._get_client()
    assert captured["raw"] is True
    assert captured["quiet"] is True


def test_extract_mapped_port_from_wrapped_vast_response():
    raw = {"instances": {"id": 883, "actual_status": "running", "public_ipaddr": "203.0.113.99", "ports": {"8190/tcp": [{"HostPort": "40123"}]}}}
    assert extract_mapped_port(raw, 8190) == 40123


def test_show_instance_unwraps_api_instances_object():
    import asyncio
    from pixelpilot.services.vast_gateway import VastSdkGateway
    class FakeClient:
        def show_instance(self, id):
            return {"instances": {"id": id, "actual_status": "running", "public_ipaddr": "203.0.113.77", "ports": {"8190/tcp": [{"HostPort": "45555"}]}}}
    async def scenario():
        gateway = VastSdkGateway("secret")
        gateway._client = FakeClient()
        ref = await gateway.show_instance(55)
        assert ref.status == "running"
        assert ref.public_ip == "203.0.113.77"
        assert ref.mapped_port == 45555
    asyncio.run(scenario())


def test_find_instances_by_label_parses_wrapped_results():
    import asyncio
    from pixelpilot.services.vast_gateway import VastSdkGateway
    class FakeClient:
        def show_instances_v1(self, **kwargs):
            assert kwargs["label"] == ["PixelPilot-abc"]
            return {"instances": [{"id": 91, "label": "PixelPilot-abc", "actual_status": "loading", "public_ipaddr": "203.0.113.91"}, {"id": 92, "label": "something-else", "actual_status": "running"}]}
    async def scenario():
        gateway = VastSdkGateway("secret")
        gateway._client = FakeClient()
        refs = await gateway.find_instances_by_label("PixelPilot-abc")
        assert len(refs) == 1
        assert refs[0].instance_id == 91
        assert refs[0].status == "loading"
    asyncio.run(scenario())
