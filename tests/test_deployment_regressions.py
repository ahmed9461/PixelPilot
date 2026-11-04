"""CPU regressions for marketplace safety, transport, context and mode routing."""
import asyncio
import base64
import contextlib
import io
import ssl
import sys
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import GpuOffer
from pixelpilot.pricing import offer_quality_rank
from pixelpilot.services.offer_policy import eligible, network_tier
from pixelpilot.services.orchestrator import Orchestrator, OfferChangedError, OfferUnavailableError
from pixelpilot.services.transport import issue_certificate, trusted_context
from pixelpilot.services.vast_gateway import build_offer_query

def offer(**kw):
    return replace(GpuOffer(1, 'RTX 5090', 32, .55, .995, 120,
        inet_down_mbps=5000, inet_up_mbps=2000, disk_space_gb=200, verified=True,
        machine_id=99, compute_cap=1200, download_usd_per_gb=0,
        raw={'num_gpus':1, 'direct_port_count':4, 'cpu_ram':128000}), **kw)

@pytest.mark.parametrize('field,value', [
    ('price_per_hour',.7000001), ('price_per_hour',float('nan')),
    ('price_per_hour',float('inf')), ('price_per_hour',0),
    ('inet_down_mbps',999), ('inet_up_mbps',499),
    ('inet_down_mbps',float('nan')), ('reliability',.97),
    ('verified',False), ('compute_cap',700), ('disk_space_gb',99),
    ('raw',{'num_gpus':2}), ('raw',{'num_gpus':1,'direct_port_count':0}),
])
def test_live_policy_fails_closed(field,value):
    assert not eligible(offer(**{field:value}),Settings(_env_file=None))

@pytest.mark.parametrize('down,up,tier',[(5000,2000,'excellent'),(3000,1000,'excellent'),(2500,1000,'preferred'),(1000,500,'standard'),(3000,499,'fallback')])
def test_network_classification(down,up,tier):
    assert network_tier(offer(inet_down_mbps=down,inet_up_mbps=up)) == tier

def test_gpu_memory_does_not_outweigh_compute_and_network():
    rank=lambda x:offer_quality_rank(x,hourly_cap=.60,download_gb=70,billed_hours=1,preferred_down_mbps=2000,preferred_up_mbps=1000)
    assert rank(offer()) < rank(offer(gpu_name='A6000',gpu_ram_gb=48,dlperf=35,compute_cap=860,inet_down_mbps=2000,inet_up_mbps=1000))
    assert rank(offer(inet_down_mbps=5000)) < rank(offer(inet_down_mbps=3000))

def test_rank_favors_reliable_hosts_and_accounts_for_full_download_fee():
    def rank(candidate):
        return offer_quality_rank(
            candidate, hourly_cap=.70, download_gb=70, billed_hours=1,
            preferred_down_mbps=2000, preferred_up_mbps=1000,
        )

    baseline = offer(reliability=.999, datacenter=True, inet_down_mbps=2000)
    costly = replace(baseline, inet_down_mbps=6000, download_usd_per_gb=.0390625)
    less_reliable = replace(baseline, reliability=.981, datacenter=False)
    assert rank(baseline) < rank(costly)
    assert rank(baseline) < rank(less_reliable)
    assert rank(baseline) < rank(replace(baseline, download_usd_per_gb=None))
    assert eligible(replace(baseline, price_per_hour=.70), Settings(_env_file=None))

def test_offer_without_total_hourly_quote_is_ineligible():
    from pixelpilot.services.vast_gateway import normalize_offer

    candidate = normalize_offer({"id": 1, "dph_base": .40})
    assert candidate.price_per_hour == 0

def test_low_network_results_are_separate_and_never_rentable(tmp_path):
    class Vast:
        def __init__(self): self.calls=[]; self.creates=0
        async def search_offers(self,q,*args,**kw):
            self.calls.append(q)
            return [offer(inet_down_mbps=700,inet_up_mbps=300)]
        async def create_instance(self,*a,**kw): self.creates+=1; raise AssertionError('must not rent fallback')
    async def scenario():
        db=Database(tmp_path/'db'); await db.init(); v=Vast()
        o=Orchestrator(Settings(_env_file=None,pixelpilot_repo_url='https://example.test/repo'),db,v)
        assert await o.offers() == []
        assert len(await db.get('offers.fallback')) == 1
        assert len(v.calls)==16
        assert 'inet_down>=3000' in v.calls[0] and 'inet_down>=2000' in v.calls[4] and 'inet_down>=1000' in v.calls[8]
        with pytest.raises(OfferUnavailableError): await o.rent(1)
        assert not v.creates
    asyncio.run(scenario())

@pytest.mark.parametrize('value',[.71,1.5,float('nan'),float('inf')])
def test_query_builder_cannot_relax_hard_ceiling(value):
    with pytest.raises(ValueError): build_offer_query(24,.98,value)

def test_tls_accepts_only_issued_certificate(tmp_path):
    async def scenario():
        cert,key=issue_certificate(); other,_=issue_certificate()
        (tmp_path/'cert').write_text(cert); (tmp_path/'key').write_bytes(base64.b64decode(key))
        server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(tmp_path/'cert',tmp_path/'key')
        async def handle(reader,writer):
            writer.write(b'ok'); await writer.drain(); writer.close(); await writer.wait_closed()
        server=await asyncio.start_server(handle,'127.0.0.1',0,ssl=server_context)
        port=server.sockets[0].getsockname()[1]
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',port,ssl=trusted_context(cert))
            assert await reader.read()==b'ok'; writer.close(); await writer.wait_closed()
            with pytest.raises(ssl.SSLCertVerificationError):
                await asyncio.open_connection('127.0.0.1',port,ssl=trusted_context(other))
        finally: server.close(); await server.wait_closed()
    asyncio.run(scenario())

def test_context_drops_old_pairs_without_truncating_vision(monkeypatch):
    from pixelpilot.services.vision_runtime import run_chat
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(inference_mode=contextlib.nullcontext))
    monkeypatch.setenv('CHAT_MAX_INPUT_TOKENS','20')
    seen=[]
    class Inputs(dict):
        def to(self,device): return self
    class Processor:
        def apply_chat_template(self,messages,**kw):
            seen.append(messages)
            return Inputs(input_ids=SimpleNamespace(shape=(1,30 if len(messages)>1 else 3)))
        def decode(self,*a,**kw): return 'answer'
    model=SimpleNamespace(device='cuda',generate=lambda **kw:[[1,2,3,4]])
    assert run_chat(model,Processor(),history=[{'role':'user','content':'old'},{'role':'assistant','content':'old reply'}],prompt='new',images=[object()],max_new_tokens=384)=='answer'
    assert len(seen)==2 and len(seen[-1])==1
    assert seen[-1][0]['content'][0]['type']=='image'

def test_gateway_only_advertises_loaded_models(monkeypatch):
    from pixelpilot import inference_gateway as g
    monkeypatch.setattr(g,'TOKEN','test')
    monkeypatch.setattr(g.state,'chat_model',object()); monkeypatch.setattr(g.state,'pipe',None)
    async def scenario():
        models=await g.models('Bearer test'); info=await g.health('Bearer test')
        assert [x['id'] for x in models['data']]==[g.CHAT_MODEL_ID]
        assert info['capabilities']=={'chat':True,'vision':True,'image':False}
    asyncio.run(scenario())
    monkeypatch.setattr(g,'CHAT_MODEL_ID','lukey03/Qwen3.5-9B-abliterated')
    assert asyncio.run(g.health('Bearer test'))['capabilities']['vision'] is False

def test_cancelled_thread_keeps_lock_until_work_finishes():
    from pixelpilot.inference_gateway import _blocking
    async def scenario():
        lock=asyncio.Lock(); started=threading.Event(); release=threading.Event()
        def work(): started.set(); release.wait(2)
        async def run():
            async with lock: await _blocking(work)
        task=asyncio.create_task(run())
        await asyncio.to_thread(started.wait,1)
        task.cancel(); await asyncio.sleep(.01)
        assert lock.locked()
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
        assert not lock.locked()
    asyncio.run(scenario())

def test_default_photo_understanding_and_explicit_edit(monkeypatch):
    from pixelpilot.bot.routers import chat
    calls=[]
    async def mode(): return 'chat'
    async def reply(*a): calls.append('vision')
    async def edit(*a): calls.append('edit')
    monkeypatch.setattr(chat,'_mode',mode); monkeypatch.setattr(chat,'_reply',reply); monkeypatch.setattr(chat,'_create_image',edit)
    async def scenario():
        await chat._handle_images(object(),'اشرح الصورة',())
        await chat._handle_images(object(),'/edit@PIXEL_PILOTBot change background',())
        assert calls==['vision','edit']
    asyncio.run(scenario())

def test_old_confirmation_cannot_accept_a_refreshed_quote(tmp_path):
    from pixelpilot.services.offer_policy import quote_fingerprint
    async def scenario():
        db=Database(tmp_path/'db'); await db.init()
        old=offer(); new=replace(old,price_per_hour=.59)
        await db.set('offers.last',[new.public_dict()])
        o=Orchestrator(Settings(_env_file=None,pixelpilot_repo_url='https://example.test/repo'),db,object())
        with pytest.raises(OfferChangedError,match='قديمة'):
            await o.rent(old.offer_id,expected_quote=quote_fingerprint(old))
        assert await db.get('instance.pending_label') is None
    asyncio.run(scenario())
