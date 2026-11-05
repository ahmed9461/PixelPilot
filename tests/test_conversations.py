"""Persistence, ownership, optimistic edits and inference contracts; no GPU."""
import asyncio
import contextlib
import json
import sys
from types import SimpleNamespace

import pytest

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.services.conversations import ConversationError, ConversationStore
from pixelpilot.services.orchestrator import Orchestrator


async def setup(path):
    db = Database(path)
    await db.init()
    return db, ConversationStore(db,1)


def test_legacy_migration_atomic_idempotent_and_lossless(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        legacy = [{"role":"user","content":"أهلًا"},{"role":"assistant","content":"مرحبًا"}]
        await db.set("chat.history.1",legacy)
        await store.init()
        active = await store.active()
        assert active["title"] == "المحادثة السابقة"
        assert (await store.context(active["id"]))["history"] == legacy
        await db.init()
        restored = ConversationStore(Database(db.path),1)
        await restored.init()
        assert (await restored.listing("conversation"))[1] == 1
        assert (await restored.active())["id"] == active["id"]
        assert await db.get("chat.history.1") == legacy
        # Clearing the migrated conversation must not resurrect legacy on restart.
        await restored.clear(active["id"])
        await restored.init()
        assert (await restored.context(active["id"]))["history"] == []
    asyncio.run(scenario())


def test_unscoped_legacy_not_copied_between_owners(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        await db.set("chat.history",[{"role":"user","content":"private"}])
        await store.init()
        other = ConversationStore(db,2)
        active = await other.active()
        assert (await other.context(active["id"]))["history"] == []
    asyncio.run(scenario())


def test_conversation_switch_pagination_sort_and_restart(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        first = await store.active()
        for i in range(6): await store.append(first["id"],f"q{i}",f"a{i}")
        second = await store.create("conversation",{"title":"ثانية"})
        await store.append(second["id"],"isolated","answer")
        assert len((await store.context(first["id"],2))["history"]) == 4
        assert (await store.context(second["id"]))["history"][0]["content"] == "isolated"
        assert (await store.listing("conversation"))[0][0]["id"] == second["id"]
        newest,count,page = await store.messages(first["id"],0)
        older,_,_ = await store.messages(first["id"],1)
        assert count == 12 and page == 0
        assert newest[-1]["content"] == "a5" and older[-1]["content"] == "a3"
        await store.select(first["id"])
        assert (await ConversationStore(Database(db.path),1).active())["id"] == first["id"]
        row = await store.get("conversation",first["id"])
        await store.update("conversation",first["id"],row["revision"],{"title":"اسم جديد"})
        assert (await store.active())["title"] == "اسم جديد"
        await store.clear(first["id"])
        assert (await store.messages(first["id"]))[1] == 0
        assert (await store.messages(second["id"]))[1] == 2
    asyncio.run(scenario())


def test_personas_prompts_composition_override_dedup_and_restore(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        first = await store.active()
        assert (await store.context(first["id"]))["system"] == ""
        prompt = await store.create("prompt",{"name":"قواعد","body":"تعليمات خاصة"})
        persona = await store.create("persona",{"name":"باحث","description":"وصف إداري لا يرسل", "body":"استخدم المصادر",
            "traits_json":json.dumps({"length":"detailed","language":"ar"}),"prompt_id":prompt["id"]})
        await store.default_persona(persona["id"],set_value=True)
        second = await store.create("conversation",{"title":"مخصصة"})
        assert (await store.get("conversation",first["id"]))["persona_id"] is None
        assert second["persona_id"] == persona["id"]
        await store.update("conversation",second["id"],second["revision"],{
            "traits_json":json.dumps({"length":"brief"}),"custom":"خصص الأمثلة","prompt_id":prompt["id"]})
        system = (await store.context(second["id"]))["system"]
        assert system == "استخدم المصادر\n\nأجب بإيجاز.\n\nأجب باللغة العربية.\n\nخصص الأمثلة\n\nتعليمات خاصة"
        assert "وصف إداري" not in system and "بتفصيل" not in system
        updated = await store.update("prompt",prompt["id"],prompt["revision"],{"body":"نص جديد"})
        assert "نص جديد" in (await store.context(second["id"]))["system"]
        disabled = await store.update("prompt",prompt["id"],updated["revision"],{"enabled":0})
        assert "نص جديد" not in (await store.context(second["id"]))["system"]
        restored = await store.restore(prompt["id"],disabled["revision"])
        assert restored["enabled"] == 1
        restored = await store.restore(prompt["id"],restored["revision"])
        # One previous version is a reversible swap, not an unbounded audit log.
        assert restored["enabled"] == 0
        assert (await store.context(first["id"]))["system"] == ""
        copy = await store.copy_persona(persona["id"])
        await store.update("persona",copy["id"],copy["revision"],{"body":"تعليمات النسخة"})
        assert (await store.get("persona",persona["id"]))["body"] == "استخدم المصادر"
    asyncio.run(scenario())


def test_prompt_body_previous_version_survives_restart(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        row = await store.create("prompt",{"name":"p","body":"old"})
        row = await store.update("prompt",row["id"],1,{"body":"new"})
        restored = await ConversationStore(Database(db.path),1).restore(row["id"],row["revision"])
        assert restored["body"] == "old"
    asyncio.run(scenario())


def test_simultaneous_edits_cannot_overwrite_one_another(tmp_path):
    async def scenario():
        _,store = await setup(tmp_path/'db')
        row = await store.create('prompt',{'name':'p','body':'original'})
        results = await asyncio.gather(*[store.update('prompt',row['id'],row['revision'],{'body':text})
                                        for text in ('first','second')],return_exceptions=True)
        assert sum(isinstance(r,dict) for r in results) == 1
        assert sum(isinstance(r,ConversationError) for r in results) == 1
        saved = await store.get('prompt',row['id'])
        assert saved['revision'] == 2 and json.loads(saved['previous_json'])['body'] == 'original'
    asyncio.run(scenario())


def test_ownership_revision_guards_and_cascade(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        other = ConversationStore(db,2)
        private = await other.create("prompt",{"name":"secret","body":"private"})
        row = await store.active()
        for action in [store.get("prompt",private["id"]),store.delete("prompt",private["id"],1),
                       store.update("conversation",row["id"],row["revision"],{"prompt_id":private["id"]}),
                       other.select(row["id"]),other.messages(row["id"]),other.context(row["id"])]:
            with pytest.raises(ConversationError): await action
        persona = await store.create("persona",{"name":"p","body":"b"})
        prompt = await store.create("prompt",{"name":"p","body":"b"})
        await store.default_persona(persona["id"],set_value=True)
        row = await store.update("conversation",row["id"],row["revision"],{"persona_id":persona["id"],"prompt_id":prompt["id"]})
        await store.append(row["id"],"q","a")
        with pytest.raises(ConversationError): await store.update("conversation",row["id"],row["revision"],{"title":"stale"})
        await store.delete("persona",persona["id"],persona["revision"])
        await store.delete("prompt",prompt["id"],prompt["revision"])
        row = await store.active()
        assert row["persona_id"] is None and row["prompt_id"] is None
        assert await store.default_persona() is None
        await store.delete("conversation",row["id"],row["revision"])
        with db._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (await store.active())["id"] != row["id"]
    asyncio.run(scenario())


@pytest.mark.parametrize("kind,values",[("persona",{"name":""}),("prompt",{"body":"x"*6001}),
    ("conversation",{"title":"x"*81}),("persona",{"traits_json":'{"hidden":"yes"}'}),
    ("conversation",{"arbitrary":"SQL"})])
def test_validation(kind,values,tmp_path):
    async def scenario():
        _,store = await setup(tmp_path/'db')
        with pytest.raises(ConversationError): await store.create(kind,values)
    asyncio.run(scenario())


def test_inference_uses_active_only_and_keeps_full_archive(tmp_path):
    async def scenario():
        db,store = await setup(tmp_path/'db')
        await db.set_many({"instance.phase":"ready","instance.id":1,"inference.url":"https://test","inference.token":"t"})
        calls=[]
        class Inference:
            async def chat(self,prompt,**kwargs): calls.append((prompt,kwargs)); return "reply"
        o = Orchestrator(Settings(_env_file=None,owner_telegram_id=1),db,object(),inference_factory=lambda *a:Inference())
        first = await store.active()
        await store.append(first["id"],"secret from first","reply")
        second = await store.create("conversation",{"title":"second"})
        await store.update("conversation",second["id"],second["revision"],{"custom":"Only my instructions"})
        for i in range(12): await store.append(second["id"],f"q{i}",f"a{i}")
        await o.chat("next")
        history = calls[-1][1]["history"]
        assert calls[-1][1]["max_new_tokens"] == 1024
        assert history[0] == {"role":"system","content":"Only my instructions"}
        assert len(history) == 17 and "secret from first" not in str(history)
        assert (await store.messages(second["id"]))[1] == 26
        await o.clear_chat_history()
        assert (await store.messages(second["id"]))[1] == 0
        assert (await store.messages(first["id"]))[1] == 2
        await store.select(first["id"])
        await o.chat("resume")
        assert calls[-1][1]["history"][0]["content"] == "secret from first"
        assert all(m["role"] != "system" for m in calls[-1][1]["history"])
        # An image album started in the first conversation may finish after a
        # switch. Its response must still be appended to the captured session.
        await store.select(second["id"])
        await o.chat("delayed album",conversation_id=first["id"])
        assert (await store.messages(second["id"]))[1] == 0
        assert (await store.messages(first["id"]))[0][-1]["content"] == "reply"
        assert (await store.active())["id"] == second["id"]
    asyncio.run(scenario())


def test_system_counted_in_budget_and_preserved_while_history_removed(monkeypatch):
    from pixelpilot.services.vision_runtime import run_chat
    monkeypatch.setitem(sys.modules,"torch",SimpleNamespace(inference_mode=contextlib.nullcontext))
    monkeypatch.setenv("CHAT_MAX_INPUT_TOKENS","10")
    seen=[]
    class Inputs(dict):
        def to(self,device): return self
    class Processor:
        def apply_chat_template(self,messages,**kw):
            seen.append(messages)
            return Inputs(input_ids=SimpleNamespace(shape=(1,20 if len(messages)>2 else 2)))
        def decode(self,*a,**kw): return "reply"
    model = SimpleNamespace(device="cuda",generate=lambda **kw:[[1,2,3]])
    run_chat(model,Processor(),history=[{"role":"system","content":"my system"},
        {"role":"user","content":"old"},{"role":"assistant","content":"old reply"}],
        prompt="new",images=[object()],max_new_tokens=1024)
    assert len(seen) == 2 and len(seen[-1]) == 2
    assert seen[-1][0]["role"] == "system"
    assert seen[-1][0]["content"][0]["text"] == "my system"
    assert seen[-1][-1]["content"][0]["type"] == "image"
    class TooLarge(Processor):
        def apply_chat_template(self,*a,**kw): return Inputs(input_ids=SimpleNamespace(shape=(1,11)))
    with pytest.raises(ValueError,match="context budget"):
        run_chat(model,TooLarge(),history=[{"role":"system","content":"large instructions"}],prompt="new",images=[],max_new_tokens=1024)


def test_gateway_system_validation_and_forwarding(monkeypatch):
    from fastapi import HTTPException
    from pixelpilot import inference_gateway as g
    monkeypatch.setattr(g,"TOKEN","test")
    monkeypatch.setattr(g,"_switch_to_chat",lambda:None)
    captured=[]
    def run(*a,**kw): captured.append(kw); return "reply"
    monkeypatch.setattr(g,"run_chat",run)
    async def scenario():
        history=[{"role":"system","content":"user authored"}]
        await g.chat_completions(g.ChatRequest(prompt="hello",history=history),authorization="Bearer test")
        assert captured[0]["history"] == history
        assert captured[0]["max_new_tokens"] == 1024
        for invalid in [[{"role":"developer","content":"bad"}],history*2,
                        [{"role":"user","content":"q"}]+history]:
            with pytest.raises(HTTPException) as exc:
                await g.chat_completions(g.ChatRequest(prompt="hello",history=invalid),authorization="Bearer test")
            assert exc.value.status_code == 422
        original=object(); monkeypatch.setattr(g.state,"chat_model",original)
        def too_long(*a,**kw): raise ValueError("context budget exceeded")
        monkeypatch.setattr(g,"run_chat",too_long)
        with pytest.raises(HTTPException) as exc:
            await g.chat_completions(g.ChatRequest(prompt="hello",history=history),authorization="Bearer test")
        assert exc.value.status_code == 422 and g.state.chat_model is original
    asyncio.run(scenario())


def test_client_refuses_to_silently_ignore_system_on_legacy_worker():
    from pixelpilot.services.inference_client import InferenceClient,InferenceError
    class Client(InferenceClient):
        supported=False
        async def _request(self,method,path,**kw):
            if path == '/health':
                return SimpleNamespace(json=lambda:{'features':{'system_instructions':self.supported}})
            assert kw['json']['history'][0] == {'role':'system','content':'mine'}
            return SimpleNamespace(json=lambda:{'choices':[{'message':{'content':'reply'}}]})
    async def scenario():
        client=Client('https://example.test','secret','Qwen/Qwen-Image-2.1')
        with pytest.raises(InferenceError,match='system instructions'):
            await client.chat('hello',history=[{'role':'system','content':'mine'}])
        client.supported=True
        assert await client.chat('hello',history=[{'role':'system','content':'mine'}]) == 'reply'
    asyncio.run(scenario())
