"""Inline conversation/settings manager. Unsaved FSM drafts vanish on restart."""
from __future__ import annotations

import json
import secrets
from html import escape

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.bot.telegram_markdown import format_model_reply
from pixelpilot.services.conversations import ConversationError, LABELS, TRAITS, compose_instructions

router = Router(name="conversations")
_orchestrator = None
NAMES = {"conversation": "المحادثات", "persona": "الشخصيات", "prompt": "البرومبتات"}
FIELDS = {"title":"عنوان المحادثة", "name":"الاسم", "description":"الوصف",
          "body":"نص التعليمات", "custom":"تعليمات المحادثة"}


class Editor(StatesGroup):
    text = State()
    preview = State()


def configure(orchestrator):
    global _orchestrator
    _orchestrator = orchestrator


def store():
    return _orchestrator.conversations


def pending_key():
    return f"chat.editor_pending.{store().owner_id}"


async def clear_draft(state):
    await state.clear()
    await _orchestrator.db.set(pending_key(),False)


class CancelDraftNavigation(BaseMiddleware):
    async def __call__(self,handler,event,data):
        state = data.get("state")
        leaving = isinstance(event,CallbackQuery) and not (event.data or "").startswith("mgr:")
        leaving = leaving or (isinstance(event,Message) and (event.text or "").split(" ")[0].split("@")[0] == "/start")
        if state and leaving:
            await clear_draft(state)
        return await handler(event,data)


class InterruptedEditor(Filter):
    async def __call__(self,message):
        return bool(await _orchestrator.db.get(pending_key(),False))


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data="mgr:"+data) for label,data in row] for row in rows])


def chunks(text, size=1600):
    # At most 3200 UTF-16 units even if every character is astral Unicode.
    return [text[i:i+size] for i in range(0,len(text),size)] or ["(فارغ)"]


def timestamp(value):
    # Keep the ISO date/time together when embedded in Arabic RTL text.
    return "<code>\u200e"+escape(value[:16].replace("T"," "))+" UTC\u200e</code>"


async def show_listing(message, kind, page=0):
    rows, count, page = await store().listing(kind, page)
    active = await store().active() if kind == "conversation" else None
    default = await store().default_persona() if kind == "persona" else None
    text = f"<b>{NAMES[kind]}</b> — {count} | الصفحة {page+1}\n"
    buttons = []
    for row in rows:
        title = row.get("title", row.get("name"))
        mark = " ✅" if (active and row["id"] == active["id"]) or row["id"] == default else ""
        if kind == "conversation":
            text += f"\n{escape(title)}{mark}\nآخر نشاط: {timestamp(row['updated_at'])}\n"
        buttons.append([(title[:45]+mark, f"open:{kind}:{row['id']}")])
    navigation = []
    if page: navigation.append(("الأحدث",f"list:{kind}:{page-1}"))
    if (page+1)*6 < count: navigation.append(("الأقدم",f"list:{kind}:{page+1}"))
    if navigation: buttons.append(navigation)
    buttons.append([("➕ محادثة جديدة" if kind == "conversation" else "➕ إنشاء",f"new:{kind}")])
    if kind == "persona":
        text += "\nالشخصية الافتراضية تطبق على المحادثات الجديدة فقط. تعديل شخصية مشتركة يؤثر في كل محادثة مرتبطة بها؛ انسخها للتخصيص المستقل."
        buttons.append([("بلا شخصية افتراضية", "nodefault")])
        buttons.append([("سمات المحادثة النشطة", "active_traits")])
    if kind == "prompt":
        text += "\nالبرومبت المشترك يؤثر في كل ارتباطاته. التعطيل يحافظ على النص والروابط."
    buttons += [[("↩️ المحادثة النشطة","active")],[("⬅️ الرئيسية","home")]]
    await message.answer(text, reply_markup=kb(buttons))


async def show_item(message, kind, item_id):
    row = await store().get(kind,item_id)
    title = row.get("title",row.get("name"))
    text = f"<b>{escape(title)}</b>\n"
    buttons = []
    if kind == "conversation":
        context = await store().context(item_id)
        persona = context["persona"]
        text += f"الشخصية: {escape(persona['name']) if persona else 'بلا شخصية'}\n"
        text += f"آخر نشاط: {timestamp(row['updated_at'])}\n"
        buttons += [[("▶️ متابعة هذه المحادثة",f"select:{item_id}")],
                    [("📜 الرسائل السابقة",f"messages:{item_id}:0")],
                    [("✏️ إعادة التسمية",f"edit:{kind}:{item_id}:title")],
                    [("🎭 اختيار الشخصية",f"pick:persona:{kind}:{item_id}:0")],
                    [("⚙️ السمات والتعليمات",f"traits:{kind}:{item_id}")],
                    [("📝 ربط برومبت",f"pick:prompt:{kind}:{item_id}:0")],
                    [("👁 معاينة التعليمات الفعالة",f"effective:{item_id}:0")]]
    else:
        text += escape(row.get("description", ""))
        if kind == "prompt": text += "\nالحالة: " + ("مفعّل" if row["enabled"] else "معطّل")
        buttons += [[("✏️ الاسم",f"edit:{kind}:{item_id}:name"), ("📝 عرض النص كاملًا",f"body:{kind}:{item_id}:0")],
                    [("✏️ تحرير النص",f"edit:{kind}:{item_id}:body")]]
        if kind == "persona":
            buttons += [[("✏️ الوصف",f"edit:{kind}:{item_id}:description")],
                        [("⚙️ السمات",f"traits:{kind}:{item_id}")],
                        [("📝 ربط برومبت",f"pick:prompt:{kind}:{item_id}:0")],
                        [("📋 نسخ الشخصية",f"copy:{item_id}"), ("⭐ جعلها الافتراضية",f"default:{item_id}")]]
        else:
            buttons += [[("تعطيل" if row["enabled"] else "تفعيل",f"toggle:{item_id}")]]
            if row["previous_json"]: buttons += [[("↶ استعادة النسخة السابقة",f"restore:{item_id}")]]
            buttons += [[("ربط بمحادثة",f"targets:conversation:{item_id}:0"),
                         ("ربط بشخصية",f"targets:persona:{item_id}:0")]]
    buttons += [[("🗑 حذف",f"delete:{kind}:{item_id}:{row['revision']}")],
                [("⬅️ رجوع",f"list:{kind}:0"), ("↩️ النشطة","active")]]
    await message.answer(text,reply_markup=kb(buttons))


async def show_pages(message, title, body, page, callback, back):
    pages = chunks(body)
    page = max(0,min(page,len(pages)-1))
    rows = []
    nav = []
    if page: nav.append(("السابق",f"{callback}:{page-1}"))
    if page+1 < len(pages): nav.append(("التالي",f"{callback}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([("⬅️ رجوع",back),("↩️ النشطة","active"),("🏠 الرئيسية","home")])
    await message.answer(f"<b>{escape(title)}</b> ({page+1}/{len(pages)})\n\n{escape(pages[page])}",reply_markup=kb(rows))


async def stage(message, state, kind, item_id, revision, values):
    store()._validate(kind,values)
    await _orchestrator.db.set(pending_key(),True)
    nonce = secrets.token_hex(4)
    await state.set_state(Editor.preview)
    await state.set_data({"kind":kind,"item_id":item_id,"revision":revision,"values":values,"nonce":nonce})
    await draft_preview(message,state,0)


async def draft_preview(message, state, page):
    data = await state.get_data()
    kind, item_id, values = data["kind"],data["item_id"],data["values"]
    lines = [f"{FIELDS[key]}: {value}" for key,value in values.items() if key in FIELDS]
    for key,source,label in [("persona_id","persona","الشخصية"),("prompt_id","prompt","البرومبت")]:
        if key in values:
            linked = await store().get(source,values[key]) if values[key] else None
            lines.append(label+": "+(linked["name"] if linked else "بلا ارتباط"))
    if "traits_json" in values:
        lines += [f"{TRAITS[k][0]}: {LABELS[v]}" for k,v in json.loads(values["traits_json"]).items()]
    if kind == "persona":
        current = await store().get(kind,item_id) if item_id else {"body":"","traits_json":"{}","prompt_id":None}
        persona = {**current,**values}
        prompts = [await store().get("prompt",persona["prompt_id"])] if persona["prompt_id"] else []
        lines += ["\nتعليمات الشخصية بعد الحفظ (قبل تخصيص المحادثة):\n" + (compose_instructions(persona,{"traits_json":"{}","custom":""},prompts) or "بلا تعليمات إضافية")]
    if kind == "prompt":
        current = await store().get(kind,item_id) if item_id else {"body":"","enabled":1}
        prompt = {**current,**values}
        lines += ["الحالة بعد الحفظ: " + ("مفعّل" if prompt["enabled"] else "معطّل"),"النص الكامل بعد الحفظ:\n" + prompt["body"]]
    # Show the exact composed instructions before applying conversation changes.
    if kind == "conversation":
        context = await store().context(item_id)
        conversation = {**context["conversation"], **values}
        persona = await store().get("persona",conversation["persona_id"]) if conversation["persona_id"] else None
        prompt_ids = list(dict.fromkeys(x for x in [persona["prompt_id"] if persona else None,conversation["prompt_id"]] if x))
        prompts = [await store().get("prompt",x) for x in prompt_ids]
        lines += ["\nالتعليمات الفعالة بعد الحفظ:\n" + (compose_instructions(persona,conversation,prompts) or "بلا تعليمات إضافية")]
    pages = chunks("\n".join(lines))
    page = max(0,min(page,len(pages)-1))
    nonce = data["nonce"]
    buttons = []
    nav = []
    if page: nav.append(("السابق",f"draft:{nonce}:{page-1}"))
    if page+1 < len(pages): nav.append(("التالي",f"draft:{nonce}:{page+1}"))
    if nav: buttons.append(nav)
    buttons += [[("💾 حفظ وتطبيق",f"save:{nonce}"),("❌ إلغاء","cancel")]]
    await message.answer(f"<b>معاينة قبل الحفظ</b> ({page+1}/{len(pages)})\n{escape(pages[page])}",reply_markup=kb(buttons))


async def ask(message,state,data):
    await _orchestrator.db.set(pending_key(),True)
    await state.set_state(Editor.text)
    await state.set_data(data)
    field = data["fields"][0]
    label = {"name":"الاسم (حتى 80 حرفًا)","title":"عنوان المحادثة (حتى 80 حرفًا)",
             "description":"الوصف (حتى 500 حرف)","body":"نص التعليمات (حتى 6000 حرف)",
             "custom":"تعليمات هذه المحادثة (حتى 6000 حرف)"}[field]
    await message.answer(f"أرسل {label}.\nأرسل - لترك النص الاختياري فارغًا. لن يُحفظ أي تغيير قبل التأكيد.",reply_markup=kb([[("❌ إلغاء","cancel")]]))


@router.message(Command("cancel"))
async def cancel_command(message: Message,state: FSMContext):
    await clear_draft(state)
    await message.answer("أُلغي الإدخال غير المحفوظ.",reply_markup=main_menu())


@router.message(StateFilter(Editor.text,Editor.preview))
async def input_text(message: Message,state: FSMContext):
    if await state.get_state() != Editor.text.state:
        await message.answer("راجع المعاينة ثم اختر حفظ أو إلغاء.",reply_markup=kb([[("❌ إلغاء","cancel")]]))
        return
    text = message.text
    if not text or text.startswith("/"):
        await message.answer("أرسل رسالة نصية لهذا الحقل، أو /cancel لإلغاء الإدخال. الصور والأوامر لا تُحفظ كتعليمات.")
        return
    data = await state.get_data()
    field = data["fields"][0]
    value = "" if text.strip() == "-" and field not in {"title","name"} else text.strip()
    try:
        store()._validate(data["kind"],{field:value})
        data["values"][field] = value
        data["fields"] = data["fields"][1:]
        if data["fields"]:
            await ask(message,state,data)
        else:
            await stage(message,state,data["kind"],data["item_id"],data["revision"],data["values"])
    except ConversationError as exc:
        await message.answer(escape(str(exc)))


@router.message(StateFilter(None),InterruptedEditor())
async def interrupted_input(message: Message,state: FSMContext):
    await clear_draft(state)
    await message.answer("أُلغي الإدخال السابق بعد إعادة التشغيل؛ لم تُحفظ هذه الرسالة ولم تُرسل للنموذج. افتح المحرر مجددًا أو أعد إرسال رسالتك للدردشة.",reply_markup=main_menu())


async def traits_screen(message, kind, item_id):
    row = await store().get(kind,item_id)
    traits = json.loads(row["traits_json"])
    buttons = []
    for key,(label,options) in TRAITS.items():
        value = LABELS.get(traits.get(key),"افتراضي / توريث")
        buttons.append([(f"{label}: {value}",f"trait:{kind}:{item_id}:{key}")])
    if kind == "conversation":
        buttons += [[("✏️ تعليمات نصية مخصصة",f"edit:{kind}:{item_id}:custom")]]
    buttons += [[("↶ استعادة السمات الافتراضية",f"reset:{kind}:{item_id}")],[("⬅️ رجوع",f"open:{kind}:{item_id}")]]
    await message.answer("<b>سمات المساعد</b>\nالافتراضي بلا تعليمات. سمات المحادثة تستبدل نفس سمة الشخصية فقط.",reply_markup=kb(buttons))


@router.callback_query(F.data.startswith("mgr:"))
async def manage(callback: CallbackQuery,state: FSMContext):
    await safe_callback_answer(callback)
    if not isinstance(callback.message,Message): return
    try:
        # Use the existing inference lock: no clear/delete/settings write can
        # race with a response being appended to its original conversation.
        async with _orchestrator._chat_lock:
            await action(callback.message,callback.data.split(":")[1:],state)
    except (ConversationError,ValueError,IndexError,KeyError) as exc:
        await clear_draft(state)
        text = str(exc) if isinstance(exc,ConversationError) else "زر غير صالح أو انتهت صلاحيته. افتح القائمة من جديد."
        await callback.message.answer(escape(text),reply_markup=main_menu())


async def action(message, args, state):
    op = args[0]
    data = await state.get_data()
    if op in {"save","draft"}:
        if await state.get_state() != Editor.preview.state or data.get("nonce") != args[1]:
            await message.answer("انتهت صلاحية هذه المعاينة. أعد فتح المحرر أو استخدم أحدث معاينة.")
            return
        if op == "draft":
            await draft_preview(message,state,int(args[2])); return
        if data["item_id"] is None:
            row = await store().create(data["kind"],data["values"])
        else:
            row = await store().update(data["kind"],data["item_id"],data["revision"],data["values"])
        await clear_draft(state)
        await message.answer("✅ حُفظت الإعدادات؛ تُطبّق على الرسائل التالية.")
        await show_item(message,data["kind"],row["id"]); return
    # Navigation explicitly abandons unsaved edits, preventing stale draft saves.
    await clear_draft(state)
    if op in {"cancel","home"}:
        await message.answer("أُلغي أي إدخال غير محفوظ." if op == "cancel" else "PixelPilot",reply_markup=main_menu())
    elif op == "list": await show_listing(message,args[1],int(args[2]))
    elif op == "open": await show_item(message,args[1],int(args[2]))
    elif op == "active":
        row = await store().active(); await show_item(message,"conversation",row["id"])
    elif op == "select":
        row = await store().select(int(args[1]))
        await _orchestrator.db.set("chat.mode","chat")
        await message.answer(f"🧠 المحادثة النشطة: {escape(row['title'])}\nأرسل رسالتك لمتابعتها.",reply_markup=kb([[("📜 السجل",f"messages:{row['id']}:0"),("⚙️ الإعدادات",f"open:conversation:{row['id']}")],[("⬅️ الرئيسية","home")]]))
    elif op == "new":
        kind = args[1]
        if kind == "conversation":
            row = await store().create(kind,{"title":"محادثة جديدة"})
            await _orchestrator.db.set("chat.mode","chat")
            await message.answer("➕ بدأت محادثة مستقلة؛ المحادثات السابقة محفوظة.",reply_markup=kb([[("⚙️ إعداداتها",f"open:conversation:{row['id']}"),("⬅️ الرئيسية","home")]]))
        else:
            fields = ["name","description","body"] if kind == "persona" else ["name","body"]
            await ask(message,state,{"kind":kind,"item_id":None,"revision":None,"values":{},"fields":fields})
    elif op == "edit":
        kind,item_id,field = args[1],int(args[2]),args[3]
        row = await store().get(kind,item_id)
        await ask(message,state,{"kind":kind,"item_id":item_id,"revision":row["revision"],"values":{},"fields":[field]})
    elif op in {"delete","confirmdelete"}:
        kind,item_id,revision = args[1],int(args[2]),int(args[3])
        row = await store().get(kind,item_id)
        if op == "delete":
            await message.answer(f"حذف {escape(row.get('title',row.get('name')))} نهائيًا؟\nحذف المحادثة يمسح رسائلها. حذف شخصية أو برومبت يفك ارتباطه فقط ويحفظ المحادثات.",reply_markup=kb([[("🗑 تأكيد الحذف",f"confirmdelete:{kind}:{item_id}:{revision}"),("إلغاء",f"open:{kind}:{item_id}")]]))
        else:
            await store().delete(kind,item_id,revision)
            await message.answer("تم الحذف."); await show_listing(message,kind)
    elif op in {"body","effective"}:
        if op == "body":
            row = await store().get(args[1],int(args[2]))
            await show_pages(message,row["name"],row["body"],int(args[3]),f"body:{args[1]}:{row['id']}",f"open:{args[1]}:{row['id']}")
        else:
            context = await store().context(int(args[1]))
            body = context["system"] or "بلا شخصية أو تعليمات إضافية."
            body = "الترتيب: تعليمات الشخصية ← السمات (المحادثة تتقدم) ← التعليمات المخصصة ← برومبت الشخصية ← برومبت المحادثة. التكرار المطابق يُرسل مرة واحدة.\n\n" + body
            await show_pages(message,"التعليمات الفعالة",body,int(args[2]),f"effective:{args[1]}",f"open:conversation:{args[1]}")
    elif op == "messages":
        item_id = int(args[1]); row = await store().get("conversation",item_id)
        rows,count,page = await store().messages(item_id,int(args[2]))
        for turn in rows:
            if turn["role"] == "assistant":
                await message.answer("🧠 PixelPilot")
                for chunk in format_model_reply(turn["content"]):
                    try:
                        await message.answer(chunk.text,entities=list(chunk.entities),parse_mode=None)
                    except TelegramBadRequest as exc:
                        if "parse entities" not in str(exc).lower(): raise
                        await message.answer(chunk.text,parse_mode=None)
            else:
                for chunk in chunks(turn["content"]):
                    await message.answer("👤 أنت\n"+escape(chunk))
        buttons = []
        if page: buttons.append(("الأحدث",f"messages:{item_id}:{page-1}"))
        if (page+1)*4 < count: buttons.append(("الأقدم",f"messages:{item_id}:{page+1}"))
        await message.answer(f"{escape(row['title'])} — {count} رسالة | الصفحة {page+1}",reply_markup=kb(([buttons] if buttons else [])+[[("▶️ متابعة",f"select:{item_id}"),("⬅️ رجوع",f"open:conversation:{item_id}")]]))
    elif op in {"default","nodefault"}:
        await store().default_persona(int(args[1]) if op == "default" else None,set_value=True)
        await message.answer("حُفظ الافتراضي للمحادثات الجديدة فقط."); await show_listing(message,"persona")
    elif op == "copy":
        row = await store().copy_persona(int(args[1])); await show_item(message,"persona",row["id"])
    elif op in {"toggle","restore"}:
        row = await store().get("prompt",int(args[1]))
        if op == "restore" and not row["previous_json"]: raise ConversationError("لا توجد نسخة سابقة.")
        values = {"enabled":1-int(row["enabled"])} if op == "toggle" else json.loads(row["previous_json"])
        await stage(message,state,"prompt",row["id"],row["revision"],values)
    elif op == "active_traits":
        row = await store().active(); await traits_screen(message,"conversation",row["id"])
    elif op == "traits": await traits_screen(message,args[1],int(args[2]))
    elif op == "trait":
        kind,item_id,key = args[1],int(args[2]),args[3]
        row = await store().get(kind,item_id)
        buttons = [[(LABELS[value],f"settrait:{kind}:{item_id}:{row['revision']}:{key}:{value}")] for value in TRAITS[key][1]]
        buttons += [[("افتراضي / توريث",f"settrait:{kind}:{item_id}:{row['revision']}:{key}:none")],[("⬅️ رجوع",f"traits:{kind}:{item_id}")]]
        await message.answer(TRAITS[key][0],reply_markup=kb(buttons))
    elif op in {"settrait","reset"}:
        kind,item_id = args[1],int(args[2]); row = await store().get(kind,item_id)
        if op == "reset": values = {"traits_json":"{}", **({"custom":""} if kind == "conversation" else {})}
        else:
            store()._check(row,int(args[3])); traits = json.loads(row["traits_json"])
            if args[5] == "none": traits.pop(args[4],None)
            else: traits[args[4]] = args[5]
            values = {"traits_json":json.dumps(traits,ensure_ascii=False)}
        await stage(message,state,kind,item_id,row["revision"],values)
    elif op in {"pick","targets"}:
        if op == "pick":
            source,kind,item_id,page = args[1],args[2],int(args[3]),int(args[4])
            target = await store().get(kind,item_id)
            rows,count,page = await store().listing(source,page)
            buttons = [[(r["name"],f"link:{kind}:{item_id}:{target['revision']}:{source}:{r['id']}")] for r in rows]
            buttons += [[("فك الارتباط",f"link:{kind}:{item_id}:{target['revision']}:{source}:0")]]
            prefix = f"pick:{source}:{kind}:{item_id}"
        else:
            kind,prompt_id,page = args[1],int(args[2]),int(args[3])
            await store().get("prompt",prompt_id)
            rows,count,page = await store().listing(kind,page)
            buttons = [[(r.get("title",r.get("name")),f"link:{kind}:{r['id']}:{r['revision']}:prompt:{prompt_id}")] for r in rows]
            prefix = f"targets:{kind}:{prompt_id}"
        nav = []
        if page: nav.append(("السابق",f"{prefix}:{page-1}"))
        if (page+1)*6 < count: nav.append(("التالي",f"{prefix}:{page+1}"))
        if nav: buttons.append(nav)
        buttons.append([("❌ إلغاء","cancel")])
        await message.answer("اختر الارتباط، ثم راجع المعاينة قبل الحفظ.",reply_markup=kb(buttons))
    elif op == "link":
        kind,item_id,revision,source,source_id = args[1],int(args[2]),int(args[3]),args[4],int(args[5])
        if source not in {"persona","prompt"} or (source == "persona" and kind != "conversation"):
            raise ConversationError("ارتباط غير صالح.")
        await stage(message,state,kind,item_id,revision,{source+"_id":source_id or None})
    else: raise ConversationError("انتهت صلاحية الزر؛ افتح القائمة من جديد.")
