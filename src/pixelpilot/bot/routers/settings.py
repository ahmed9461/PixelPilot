from __future__ import annotations

from html import escape
from typing import Any

from aiogram import Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.services.assistant_settings import (
    DEFAULT_STATE,
    GROUPS,
    context_policy,
    effective_system_prompt,
    get_prompt,
    get_state,
    reset_all,
    reset_prompt,
    set_prompt,
    set_state,
)
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="assistant_settings")
_orchestrator: Orchestrator | None = None
_pending_edit: tuple[str, str] | None = None


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Assistant settings router not configured")
    return _orchestrator


def _label(group: str, key: str) -> str:
    options = GROUPS[group]
    item = next((item for item in options if item.key == key), options[0])
    return item.label


def _home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎭 روح المساعد", callback_data="assistant:group:persona"),
                InlineKeyboardButton(text="⚡ السمة", callback_data="assistant:group:tone"),
            ],
            [
                InlineKeyboardButton(text="🧠 الاستدلال", callback_data="assistant:group:reasoning"),
                InlineKeyboardButton(text="🧾 التنسيق", callback_data="assistant:group:format"),
            ],
            [
                InlineKeyboardButton(text="🎚️ التوليد", callback_data="assistant:generation"),
                InlineKeyboardButton(text="🧠 السياق", callback_data="assistant:context"),
            ],
            [
                InlineKeyboardButton(text="📝 البرومتات", callback_data="assistant:prompts"),
                InlineKeyboardButton(text="🌐 اللغة", callback_data="assistant:group:language"),
            ],
            [InlineKeyboardButton(text="⬅️ الرئيسية", callback_data="home")],
        ]
    )


async def _settings_text() -> str:
    state = await get_state(orch().db)
    return (
        "⚙️ <b>إعدادات المساعد</b>\n\n"
        "هنا تغيّر شخصية المساعد وطريقة الرد والإعدادات المتقدمة بدون تعديل ملفات السيرفر.\n\n"
        f"🎭 الروح: <b>{escape(_label('persona', str(state['persona'])))}</b>\n"
        f"⚡ السمة: <b>{escape(_label('tone', str(state['tone'])))}</b>\n"
        f"🧠 الاستدلال: <b>{escape(_label('reasoning', str(state['reasoning'])))}</b>\n"
        f"🧾 التنسيق: <b>{escape(_label('format', str(state['format'])))}</b>\n"
        f"🌐 اللغة: <b>{escape(_label('language', str(state['language'])))}</b>\n"
        f"🎨 الإبداع: <b>{int(state['creativity_pct'])}%</b>\n"
        f"🧪 التنوع: <b>{int(state['diversity_pct'])}%</b>\n"
        f"📏 طول الرد: <b>{int(state['response_length_pct'])}%</b>"
    )


@router.callback_query(lambda q: q.data == "assistant:settings")
async def settings_home(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(await _settings_text(), reply_markup=_home_keyboard())


def _group_keyboard(group: str, selected: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for option in GROUPS[group]:
        mark = "✓ " if option.key == selected else ""
        current.append(
            InlineKeyboardButton(
                text=f"{mark}{option.label}",
                callback_data=f"assistant:select:{group}:{option.key}",
            )
        )
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([InlineKeyboardButton(text="✏️ تعديل البرومت المحدد", callback_data=f"assistant:prompt:current:{group}")])
    rows.append([InlineKeyboardButton(text="⬅️ الإعدادات", callback_data="assistant:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:group:"))
async def show_group(callback: CallbackQuery) -> None:
    group = callback.data.rsplit(":", 1)[1]
    if group not in GROUPS:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    await safe_callback_answer(callback)
    state = await get_state(orch().db)
    selected = str(state[group])
    titles = {
        "persona": "🎭 <b>روح المساعد</b>\n\nاختر الشخصية الأساسية:",
        "tone": "⚡ <b>السمة</b>\n\nاختر نبرة الرد:",
        "reasoning": "🧠 <b>الاستدلال</b>\n\nاختر عمق معالجة الأسئلة:",
        "format": "🧾 <b>التنسيق</b>\n\nاختر طريقة تنظيم الرد:",
        "language": "🌐 <b>اللغة</b>\n\nالتلقائي يترك اللغة للسياق والرسالة:",
    }
    await callback.message.edit_text(
        titles[group],
        reply_markup=_group_keyboard(group, selected),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:select:"))
async def select_group(callback: CallbackQuery) -> None:
    _, _, group, key = callback.data.split(":", 3)
    if group not in GROUPS or key not in {item.key for item in GROUPS[group]}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    await set_state(orch().db, group, key)
    await safe_callback_answer(callback, "تم الحفظ")
    state = await get_state(orch().db)
    await callback.message.edit_reply_markup(reply_markup=_group_keyboard(group, str(state[group])))


def _generation_keyboard(state: dict[str, Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    specs = (
        ("creativity_pct", "🎨 الإبداع", 10),
        ("diversity_pct", "🧪 التنوع", 5),
        ("response_length_pct", "📏 طول الرد", 10),
    )
    for name, label, step in specs:
        value = int(state[name])
        rows.append([
            InlineKeyboardButton(text="−", callback_data=f"assistant:adjust:{name}:-{step}"),
            InlineKeyboardButton(text=f"{label} {value}%", callback_data="assistant:generation"),
            InlineKeyboardButton(text="+", callback_data=f"assistant:adjust:{name}:{step}"),
        ])
    rows.extend([
        [InlineKeyboardButton(text="♻️ استعادة القيم الافتراضية", callback_data="assistant:generation:reset")],
        [InlineKeyboardButton(text="⬅️ الإعدادات", callback_data="assistant:settings")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_generation(callback: CallbackQuery) -> None:
    state = await get_state(orch().db)
    await callback.message.edit_text(
        "🎚️ <b>إعدادات التوليد</b>\n\n"
        "🎨 الإبداع: يزيد التنوع والحرية في الصياغة.\n"
        "🧪 التنوع: يوسّع أو يضيّق نطاق الكلمات المحتملة.\n"
        "📏 طول الرد: يحدد الحد التقريبي لطول الإجابة.\n\n"
        "القيمة الافتراضية للإبداع 0% لأنها الأكثر ثباتًا.",
        reply_markup=_generation_keyboard(state),
    )


@router.callback_query(lambda q: q.data == "assistant:generation")
async def generation(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await _show_generation(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:adjust:"))
async def adjust_generation(callback: CallbackQuery) -> None:
    _, _, name, delta_text = callback.data.split(":", 3)
    if name not in {"creativity_pct", "diversity_pct", "response_length_pct"}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    state = await get_state(orch().db)
    value = int(state[name]) + int(delta_text)
    minimum = 10 if name in {"diversity_pct", "response_length_pct"} else 0
    value = max(minimum, min(100, value))
    await set_state(orch().db, name, value)
    await safe_callback_answer(callback, f"{value}%")
    await _show_generation(callback)


@router.callback_query(lambda q: q.data == "assistant:generation:reset")
async def reset_generation(callback: CallbackQuery) -> None:
    for name in ("creativity_pct", "diversity_pct", "response_length_pct"):
        await set_state(orch().db, name, DEFAULT_STATE[name])
    await safe_callback_answer(callback, "تمت الاستعادة")
    await _show_generation(callback)


def _context_keyboard(enabled: bool, count: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"Memory {'✓' if enabled else '○'}",
            callback_data="assistant:context:toggle",
        )],
        [
            InlineKeyboardButton(text=f"{'✓ ' if count == 4 else ''}4", callback_data="assistant:context:size:4"),
            InlineKeyboardButton(text=f"{'✓ ' if count == 8 else ''}8", callback_data="assistant:context:size:8"),
            InlineKeyboardButton(text=f"{'✓ ' if count == 12 else ''}12", callback_data="assistant:context:size:12"),
            InlineKeyboardButton(text=f"{'✓ ' if count == 20 else ''}20", callback_data="assistant:context:size:20"),
        ],
        [InlineKeyboardButton(text="🗑 مسح سياق المحادثة", callback_data="assistant:context:clear")],
        [InlineKeyboardButton(text="⬅️ الإعدادات", callback_data="assistant:settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_context(callback: CallbackQuery) -> None:
    enabled, count = await context_policy(
        orch().db,
        default_messages=orch().settings.chat_history_messages,
    )
    await callback.message.edit_text(
        "🧠 <b>السياق</b>\n\n"
        f"الحالة: <b>{'مفعّل' if enabled else 'متوقف'}</b>\n"
        f"الحد الحالي: <b>{count} رسالة</b>\n\n"
        "السياق هنا للمحادثة الحالية فقط ويمكن مسحه في أي وقت.",
        reply_markup=_context_keyboard(enabled, count),
    )


@router.callback_query(lambda q: q.data == "assistant:context")
async def context_settings(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await _show_context(callback)


@router.callback_query(lambda q: q.data == "assistant:context:toggle")
async def context_toggle(callback: CallbackQuery) -> None:
    state = await get_state(orch().db)
    await set_state(orch().db, "context_enabled", not bool(state["context_enabled"]))
    await safe_callback_answer(callback, "تم")
    await _show_context(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:context:size:"))
async def context_size(callback: CallbackQuery) -> None:
    count = int(callback.data.rsplit(":", 1)[1])
    await set_state(orch().db, "context_messages", max(1, min(40, count)))
    await safe_callback_answer(callback, "تم الحفظ")
    await _show_context(callback)


@router.callback_query(lambda q: q.data == "assistant:context:clear")
async def context_clear(callback: CallbackQuery) -> None:
    from pixelpilot.bot.routers.chat import clear_history

    clear_history()
    await safe_callback_answer(callback, "تم مسح السياق")
    await _show_context(callback)


def _prompts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧩 البرومت المخصص", callback_data="assistant:prompt:custom")],
            [
                InlineKeyboardButton(text="🎭 برومت الشخصية", callback_data="assistant:prompt:current:persona"),
                InlineKeyboardButton(text="⚡ برومت السمة", callback_data="assistant:prompt:current:tone"),
            ],
            [
                InlineKeyboardButton(text="🧠 برومت الاستدلال", callback_data="assistant:prompt:current:reasoning"),
                InlineKeyboardButton(text="🧾 برومت التنسيق", callback_data="assistant:prompt:current:format"),
            ],
            [InlineKeyboardButton(text="🌐 برومت اللغة", callback_data="assistant:prompt:current:language")],
            [InlineKeyboardButton(text="👁 عرض البرومت الفعّال", callback_data="assistant:prompt:effective")],
            [InlineKeyboardButton(text="📤 تصدير البرومت الفعّال", callback_data="assistant:prompt:export")],
            [InlineKeyboardButton(text="♻️ إعادة كل الإعدادات الافتراضية", callback_data="assistant:reset_all")],
            [InlineKeyboardButton(text="⬅️ الإعدادات", callback_data="assistant:settings")],
        ]
    )


@router.callback_query(lambda q: q.data == "assistant:prompts")
async def prompts(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "📝 <b>البرومتات</b>\n\n"
        "كل جزء قابل للتعديل من هنا. التغيير يُحفظ فورًا ويستخدم في الرسائل التالية.",
        reply_markup=_prompts_keyboard(),
    )


def _prompt_actions(group: str, key: str, *, custom: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text="✏️ تعديل/استبدال",
        callback_data=("assistant:prompt:edit:custom:base" if custom else f"assistant:prompt:edit:{group}:{key}"),
    )]]
    if not custom:
        rows.append([InlineKeyboardButton(text="↩️ استعادة الافتراضي", callback_data=f"assistant:prompt:reset:{group}:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ البرومتات", callback_data="assistant:prompts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(lambda q: q.data == "assistant:prompt:custom")
async def custom_prompt(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    state = await get_state(orch().db)
    prompt = str(state.get("custom_prompt") or "")
    shown = escape(prompt) if prompt else "<i>غير مفعّل</i>"
    await callback.message.edit_text(
        f"🧩 <b>البرومت المخصص</b>\n\n{shown}",
        reply_markup=_prompt_actions("custom", "base", custom=True),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:current:"))
async def current_prompt(callback: CallbackQuery) -> None:
    group = callback.data.rsplit(":", 1)[1]
    if group not in GROUPS:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    state = await get_state(orch().db)
    key = str(state[group])
    prompt = await get_prompt(orch().db, group, key)
    shown = escape(prompt) if prompt else "<i>لا يوجد برومت لهذا الخيار</i>"
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        f"{escape(_label(group, key))}\n\n{shown}",
        reply_markup=_prompt_actions(group, key),
    )


@router.callback_query(lambda q: q.data == "assistant:prompt:effective")
async def effective_prompt_view(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    prompt = await effective_system_prompt(orch().db)
    shown = escape(prompt) if prompt else "<i>لا يوجد برومت فعّال حاليًا.</i>"
    if len(shown) > 3500:
        shown = shown[:3500] + "…"
    await callback.message.edit_text(
        f"👁 <b>البرومت الفعّال</b>\n\n{shown}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 تصدير كامل", callback_data="assistant:prompt:export")],
            [InlineKeyboardButton(text="⬅️ البرومتات", callback_data="assistant:prompts")],
        ]),
    )


@router.callback_query(lambda q: q.data == "assistant:prompt:export")
async def export_prompt(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري التصدير")
    prompt = await effective_system_prompt(orch().db)
    body = prompt or "لا يوجد برومت فعّال حاليًا."
    await callback.message.answer_document(
        BufferedInputFile(body.encode("utf-8"), filename="pixelpilot-effective-prompt.txt"),
        caption="📤 البرومت الفعّال الحالي",
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:edit:"))
async def edit_prompt(callback: CallbackQuery) -> None:
    global _pending_edit
    _, _, _, group, key = callback.data.split(":", 4)
    if group != "custom" and (group not in GROUPS or key not in {item.key for item in GROUPS[group]}):
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    _pending_edit = (group, key)
    await safe_callback_answer(callback, "أرسل البرومت الجديد")
    await callback.message.edit_text(
        "✏️ <b>تعديل البرومت</b>\n\n"
        "أرسل الآن النص الجديد كاملًا في رسالة واحدة.\n"
        "أرسل <code>-</code> لجعله فارغًا، أو /cancel للإلغاء."
    )


@router.message(lambda message: _pending_edit is not None and bool(message.text))
async def receive_prompt_edit(message: Message) -> None:
    global _pending_edit
    target = _pending_edit
    if target is None:
        return
    text = (message.text or "").strip()
    if text == "/cancel":
        _pending_edit = None
        await message.answer("تم إلغاء التعديل.", reply_markup=main_menu())
        return
    value = "" if text == "-" else message.text or ""
    group, key = target
    if group == "custom":
        await set_state(orch().db, "custom_prompt", value)
    else:
        await set_prompt(orch().db, group, key, value)
    _pending_edit = None
    await message.answer("✅ تم حفظ البرومت الجديد.", reply_markup=_prompts_keyboard())


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:reset:"))
async def restore_prompt(callback: CallbackQuery) -> None:
    _, _, _, group, key = callback.data.split(":", 4)
    if group not in GROUPS:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    await reset_prompt(orch().db, group, key)
    await safe_callback_answer(callback, "تمت الاستعادة")
    state = await get_state(orch().db)
    selected = str(state[group])
    prompt = await get_prompt(orch().db, group, selected)
    shown = escape(prompt) if prompt else "<i>لا يوجد برومت لهذا الخيار</i>"
    await callback.message.edit_text(
        f"{escape(_label(group, selected))}\n\n{shown}",
        reply_markup=_prompt_actions(group, selected),
    )


@router.callback_query(lambda q: q.data == "assistant:reset_all")
async def reset_all_settings(callback: CallbackQuery) -> None:
    from pixelpilot.bot.routers.chat import clear_history

    await reset_all(orch().db)
    clear_history()
    await safe_callback_answer(callback, "تمت إعادة الإعدادات")
    await callback.message.edit_text(await _settings_text(), reply_markup=_home_keyboard())
