"""Dispatch real aiogram updates through owner middleware and FSM, fake Telegram I/O."""
import asyncio
from datetime import UTC,datetime

from aiogram import Bot,Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery,GetMe,SendMessage
from aiogram.types import CallbackQuery,Chat,Message,Update,User

from pixelpilot.bot.middleware import OwnerOnlyMiddleware
from pixelpilot.bot.routers import conversations as ui
from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.services.orchestrator import Orchestrator


class TelegramSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.messages=[]
    async def close(self): pass
    async def stream_content(self,*a,**kw):
        yield b""
    async def make_request(self,bot,method,timeout=None):
        if isinstance(method,AnswerCallbackQuery): return True
        if isinstance(method,GetMe): return User(id=123,is_bot=True,first_name="PixelPilot",username="pixelpilot_test_bot")
        if isinstance(method,SendMessage):
            message = Message(message_id=len(self.messages)+1,date=datetime.now(UTC),chat=Chat(id=1,type="private"),
                              text=method.text,reply_markup=method.reply_markup)
            # Validate outbound text in Telegram UTF-16 units, including emoji.
            assert len(method.text.encode('utf-16-le'))//2 <= 4096
            self.messages.append(message)
            return message
        raise AssertionError(type(method))


def test_conversation_persona_prompt_workflows_dispatch(tmp_path):
    async def scenario():
        db=Database(tmp_path/'db'); await db.init()
        orch=Orchestrator(Settings(_env_file=None,owner_telegram_id=1),db,object())
        ui.configure(orch)
        session=TelegramSession()
        bot=Bot("123:TEST",session=session,default=DefaultBotProperties(parse_mode="HTML"))
        dp=Dispatcher(events_isolation=SimpleEventIsolation())
        dp.update.middleware(OwnerOnlyMiddleware(1))
        dp.callback_query.outer_middleware(ui.CancelDraftNavigation())
        dp.message.outer_middleware(ui.CancelDraftNavigation())
        dp.include_router(ui.router)
        counter=0
        async def send(*,text=None,callback=None,user=1,photo=False):
            nonlocal counter
            counter+=1
            who=User(id=user,is_bot=False,first_name="Owner")
            message=Message(message_id=counter,date=datetime.now(UTC),chat=Chat(id=1,type="private"),from_user=who,
                            text=text,photo=[{"file_id":"file","file_unique_id":"unique","width":1,"height":1}] if photo else None)
            update=Update(update_id=counter,callback_query=CallbackQuery(id=str(counter),from_user=who,chat_instance="x",message=message,data=callback)) if callback else Update(update_id=counter,message=message)
            await dp.feed_update(bot,update)
        def button(prefix):
            return next(b.callback_data for message in reversed(session.messages) if message.reply_markup
                        for row in message.reply_markup.inline_keyboard for b in row if b.callback_data.startswith(prefix))
        try:
            await send(callback="mgr:list:conversation:0",user=2)
            assert not session.messages
            await send(callback="mgr:new:conversation")
            first=await orch.conversations.active()
            await orch.conversations.append(first['id'],'old question','old answer')
            await send(callback="mgr:new:conversation")
            second=await orch.conversations.active()
            assert first['id'] != second['id']
            await send(callback=f"mgr:select:{first['id']}")
            await send(callback=f"mgr:messages:{first['id']}:0")
            assert any('old answer' in m.text for m in session.messages)
            await send(callback=f"mgr:edit:conversation:{first['id']}:title")
            await send(photo=True)
            assert 'رسالة نصية' in session.messages[-1].text
            await send(text='Renamed')
            assert (await orch.conversations.active())['title'] != 'Renamed'
            save=button('mgr:save:')
            await send(callback=save)
            assert (await orch.conversations.active())['title'] == 'Renamed'
            await send(callback=save)
            assert 'انتهت صلاحية' in session.messages[-1].text
            # Create a prompt, cancel a replacement body, then save and restore.
            await send(callback='mgr:new:prompt'); await send(text='قواعدي'); await send(text='قل الحقيقة فقط')
            await send(callback=button('mgr:save:'))
            prompt=(await orch.conversations.listing('prompt'))[0][0]
            await send(callback=f"mgr:edit:prompt:{prompt['id']}:body"); await send(text='discard this')
            stale=button('mgr:save:'); await send(callback='mgr:cancel'); await send(callback=stale)
            assert (await orch.conversations.get('prompt',prompt['id']))['body'] == 'قل الحقيقة فقط'
            await send(callback=f"mgr:edit:prompt:{prompt['id']}:body"); await send(text='قواعد جديدة')
            await send(callback=button('mgr:save:'))
            await send(callback=f"mgr:restore:{prompt['id']}"); await send(callback=button('mgr:save:'))
            assert (await orch.conversations.get('prompt',prompt['id']))['body'] == 'قل الحقيقة فقط'
            # Persona creation is a three-field FSM; description is metadata.
            await send(callback='mgr:new:persona'); await send(text='باحث'); await send(text='وصف شخصي'); await send(text='اذكر المصادر')
            await send(callback=button('mgr:save:'))
            persona=(await orch.conversations.listing('persona'))[0][0]
            await send(callback=f"mgr:copy:{persona['id']}")
            assert (await orch.conversations.listing('persona'))[1] == 2
            await send(callback=f"mgr:default:{persona['id']}")
            assert await orch.conversations.default_persona() == persona['id']
            await send(callback=f"mgr:pick:persona:conversation:{first['id']}:0")
            row=await orch.conversations.active()
            await send(callback=f"mgr:link:conversation:{row['id']}:{row['revision']}:persona:{persona['id']}")
            assert (await orch.conversations.active())['persona_id'] is None
            await send(callback=button('mgr:save:'))
            await send(callback=f"mgr:pick:prompt:conversation:{row['id']}:0")
            await send(callback=button('mgr:link:conversation:'))
            await send(callback=button('mgr:save:'))
            await send(callback=f"mgr:traits:conversation:{row['id']}")
            await send(callback=f"mgr:trait:conversation:{row['id']}:length")
            await send(callback=button(f"mgr:settrait:conversation:{row['id']}"))
            await send(callback=button('mgr:save:'))
            effective=(await orch.conversations.context(row['id']))['system']
            assert 'اذكر المصادر' in effective and 'قل الحقيقة فقط' in effective and 'بإيجاز' in effective
            await send(callback=f"mgr:effective:{row['id']}:0")
            assert 'تعليمات' in session.messages[-1].text
            # Revision race while editing must keep the newer value.
            await send(callback=f"mgr:edit:conversation:{row['id']}:title"); await send(text='stale')
            current=await orch.conversations.active()
            await orch.conversations.update('conversation',row['id'],current['revision'],{'title':'newer'})
            await send(callback=button('mgr:save:'))
            assert (await orch.conversations.active())['title'] == 'newer'
            # Restart loses only the draft: intercept next input, never forward it.
            await send(callback=f"mgr:edit:conversation:{row['id']}:custom")
            ctx=dp.fsm.get_context(bot=bot,chat_id=1,user_id=1)
            await ctx.clear()
            await send(text='sensitive unfinished instructions')
            assert 'بعد إعادة التشغيل' in session.messages[-1].text
            assert (await orch.conversations.active())['custom'] == ''
            await send(callback=f"mgr:delete:conversation:{second['id']}:{second['revision']}")
            assert (await orch.conversations.get('conversation',second['id']))['id'] == second['id']
            await send(callback=button('mgr:confirmdelete:'))
            assert (await orch.conversations.listing('conversation'))[1] == 1
        finally:
            ui.router._parent_router=None
            await dp.storage.close(); await dp.fsm.events_isolation.close(); await bot.session.close()
    asyncio.run(scenario())
