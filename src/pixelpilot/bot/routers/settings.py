from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Literal

from aiogram import Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from pixelpilot.bot.callbacks import (
    safe_callback_answer,
    safe_edit_reply_markup,
    safe_edit_text,
)
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

PromptOrigin = Literal["group", "hub"]


@dataclass(slots=True)
class PendingPromptEdit:
    group: str
    key: str
    origin: PromptOrigin


_pending_edit: PendingPromptEdit | None = None


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


def _cancel_pending() -> None:
    global _pending_edit
    _pending_edit = None


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
        "غيّر الشخصية وطريقة الرد والإعدادات المتقدمة من هنا مباشرة.\n\n"
        f"🎭 الروح: <b>{escape(_label('persona', str(state['persona'])))}</b>\n"
        f"⚡ السمة: <b>{escape(_label('tone', str(state['tone'])))}</b>\n"
        f"🧠 الاستدلال: <b>{escape(_label('reasoning', str(state['reasoning'])))}</b>\n"
        f"🧾 التنسيق: <b>{escape(_label('format', str(state['format'])))}</b>\n"
        f"🌐 اللغة: <b>{escape(_label('language', str(state['language'])))}</b>\n"
        f"🎨 الإبداع: <b>{int(state['creativity_pct'])}%</b>\n"
        f"🧪 التنوع: <b>{int(state['diversity_pct'])}%</b>\n"
        f"📏 طول الرد: <b>{int(state['response_length_pct'])}%</b>"
    )


@router.callback_query(lambda q: q.data == "assistant:noop")
async def noop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)


@router.callback_query(lambda q: q.data == "assistant:settings")
async def settings_home(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    await safe_edit_text(callback.message, await _settings_text(), reply_markup=_home_keyboard())


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
    rows.append([
        InlineKeyboardButton(
            text="✏️ عرض/تعديل برومت الخيار",
            callback_data=f"assistant:prompt:open:{group}:group",
        )
    ])
    rows.append([InlineKeyboardButton(text="⬅️ إعدادات المساعد", callback_data="assistant:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _group_title(group: str) -> str:
    return {
        "persona": "🎭 <b>روح المساعد</b>\n\nاختر الشخصية الأساسية:",
        "tone": "⚡ <b>السمة</b>\n\nاختر نبرة الرد:",
        "reasoning": "🧠 <b>الاستدلال</b>\n\nاختر عمق معالجة الأسئلة:",
        "format": "🧾 <b>التنسيق</b>\n\nاختر طريقة تنظيم الرد:",
        "language": "🌐 <b>اللغة</b>\n\nالتلقائي يترك اللغة للسياق والرسالة:",
    }[group]


async def _show_group(callback: CallbackQuery, group: str) -> None:
    state = await get_state(orch().db)
    await safe_edit_text(
        callback.message,
        _group_title(group),
        reply_markup=_group_keyboard(group, str(state[group])),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:group:"))
async def show_group(callback: CallbackQuery) -> None:
    _cancel_pending()
    group = callback.data.rsplit(":", 1)[1]
    if group not in GROUPS:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    await safe_callback_answer(callback)
    await _show_group(callback, group)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:select:"))
async def select_group(callback: CallbackQuery) -> None:
    _cancel_pending()
    _, _, group, key = callback.data.split(":", 3)
    if group not in GROUPS or key not in {item.key for item in GROUPS[group]}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    state = await get_state(orch().db)
    if str(state[group]) == key:
        await safe_callback_answer(callback, "محدد بالفعل")
        return
    await safe_callback_answer(callback, "تم الحفظ")
    await set_state(orch().db, group, key)
    await safe_edit_reply_markup(callback.message, reply_markup=_group_keyboard(group, key))


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
            InlineKeyboardButton(text=f"{label} {value}%", callback_data="assistant:noop"),
            InlineKeyboardButton(text="+", callback_data=f"assistant:adjust:{name}:{step}"),
        ])
    rows.extend([
        [InlineKeyboardButton(text="♻️ استعادة القيم الافتراضية", callback_data="assistant:generation:reset")],
        [InlineKeyboardButton(text="⬅️ إعدادات المساعد", callback_data="assistant:settings")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_generation(callback: CallbackQuery, state: dict[str, Any] | None = None) -> None:
    state = state or await get_state(orch().db)
    await safe_edit_text(
        callback.message,
        "🎚️ <b>إعدادات التوليد</b>\n\n"
        "🎨 الإبداع: يرفع حرية الصياغة والعشوائية تدريجيًا.\n"
        "🧪 التنوع: يوسع أو يضيّق نطاق الاحتمالات اللغوية.\n"
        "📏 طول الرد: يتحكم بالحد الأقصى التقريبي للإجابة.\n\n"
        "الإبداع 0% هو الوضع الأكثر ثباتًا.",
        reply_markup=_generation_keyboard(state),
    )


@router.callback_query(lambda q: q.data == "assistant:generation")
async def generation(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    await _show_generation(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:adjust:"))
async def adjust_generation(callback: CallbackQuery) -> None:
    _cancel_pending()
    _, _, name, delta_text = callback.data.split(":", 3)
    if name not in {"creativity_pct", "diversity_pct", "response_length_pct"}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    state = await get_state(orch().db)
    old_value = int(state[name])
    minimum = 10 if name in {"diversity_pct", "response_length_pct"} else 0
    value = max(minimum, min(100, old_value + int(delta_text)))
    if value == old_value:
        await safe_callback_answer(callback, f"{value}%")
        return
    await safe_callback_answer(callback, f"{value}%")
    await set_state(orch().db, name, value)
    state[name] = value
    await _show_generation(callback, state)


@router.callback_query(lambda q: q.data == "assistant:generation:reset")
async def reset_generation(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback, "تمت الاستعادة")
    await orch().db.set_many({
        "assistant.state.creativity_pct": DEFAULT_STATE["creativity_pct"],
        "assistant.state.diversity_pct": DEFAULT_STATE["diversity_pct"],
        "assistant.state.response_length_pct": DEFAULT_STATE["response_length_pct"],
    })
    state = await get_state(orch().db)
    await _show_generation(callback, state)


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
        [InlineKeyboardButton(text="⬅️ إعدادات المساعد", callback_data="assistant:settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_context(callback: CallbackQuery, *, enabled: bool | None = None, count: int | None = None) -> None:
    if enabled is None or count is None:
        enabled, count = await context_policy(
            orch().db,
            default_messages=orch().settings.chat_history_messages,
        )
    await safe_edit_text(
        callback.message,
        "🧠 <b>السياق</b>\n\n"
        f"الحالة: <b>{'مفعّل' if enabled else 'متوقف'}</b>\n"
        f"الحد الحالي: <b>{count} رسالة</b>\n\n"
        "السياق للمحادثة الحالية فقط ويمكن مسحه في أي وقت.",
        reply_markup=_context_keyboard(bool(enabled), int(count)),
    )


@router.callback_query(lambda q: q.data == "assistant:context")
async def context_settings(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    await _show_context(callback)


@router.callback_query(lambda q: q.data == "assistant:context:toggle")
async def context_toggle(callback: CallbackQuery) -> None:
    _cancel_pending()
    state = await get_state(orch().db)
    enabled = not bool(state["context_enabled"])
    count = int(state["context_messages"])
    await safe_callback_answer(callback, "تم")
    await set_state(orch().db, "context_enabled", enabled)
    await _show_context(callback, enabled=enabled, count=count)


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:context:size:"))
async def context_size(callback: CallbackQuery) -> None:
    _cancel_pending()
    count = max(1, min(40, int(callback.data.rsplit(":", 1)[1])))
    state = await get_state(orch().db)
    if int(state["context_messages"]) == count:
        await safe_callback_answer(callback, "محدد بالفعل")
        return
    await safe_callback_answer(callback, "تم الحفظ")
    await set_state(orch().db, "context_messages", count)
    await _show_context(callback, enabled=bool(state["context_enabled"]), count=count)


@router.callback_query(lambda q: q.data == "assistant:context:clear")
async def context_clear(callback: CallbackQuery) -> None:
    _cancel_pending()
    from pixelpilot.bot.routers.chat import clear_history

    clear_history()
    await safe_callback_answer(callback, "تم مسح السياق")
    await _show_context(callback)


def _prompts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧩 البرومت المخصص", callback_data="assistant:prompt:custom")],
            [
                InlineKeyboardButton(text="🎭 برومت الشخصية", callback_data="assistant:prompt:open:persona:hub"),
                InlineKeyboardButton(text="⚡ برومت السمة", callback_data="assistant:prompt:open:tone:hub"),
            ],
            [
                InlineKeyboardButton(text="🧠 برومت الاستدلال", callback_data="assistant:prompt:open:reasoning:hub"),
                InlineKeyboardButton(text="🧾 برومت التنسيق", callback_data="assistant:prompt:open:format:hub"),
            ],
            [InlineKeyboardButton(text="🌐 برومت اللغة", callback_data="assistant:prompt:open:language:hub")],
            [InlineKeyboardButton(text="👁 عرض البرومت الفعّال", callback_data="assistant:prompt:effective")],
            [InlineKeyboardButton(text="📤 تصدير البرومت الفعّال", callback_data="assistant:prompt:export")],
            [InlineKeyboardButton(text="♻️ إعادة كل الإعدادات الافتراضية", callback_data="assistant:reset_all")],
            [InlineKeyboardButton(text="⬅️ إعدادات المساعد", callback_data="assistant:settings")],
        ]
    )


@router.callback_query(lambda q: q.data == "assistant:prompts")
async def prompts(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        "📝 <b>البرومتات</b>\n\n"
        "كل ملف سلوك قابل للعرض والتعديل والاستبدال والاستعادة من هنا. "
        "التغييرات تطبق على الرسالة التالية مباشرة.",
        reply_markup=_prompts_keyboard(),
    )


def _origin_back_callback(group: str, origin: PromptOrigin) -> str:
    return f"assistant:group:{group}" if origin == "group" else "assistant:prompts"


def _origin_back_label(origin: PromptOrigin) -> str:
    return "⬅️ رجوع للقسم" if origin == "group" else "⬅️ البرومتات"


def _prompt_actions(
    group: str,
    key: str,
    *,
    origin: PromptOrigin,
    custom: bool = False,
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text="✏️ تعديل/استبدال",
        callback_data=(
            f"assistant:prompt:edit:custom:base:{origin}"
            if custom
            else f"assistant:prompt:edit:{group}:{key}:{origin}"
        ),
    )]]
    if not custom:
        rows.append([
            InlineKeyboardButton(
                text="↩️ استعادة النسخة الأصلية",
                callback_data=f"assistant:prompt:reset:{group}:{key}:{origin}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text=_origin_back_label(origin),
            callback_data=_origin_back_callback(group, origin),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_prompt(callback: CallbackQuery, group: str, key: str, origin: PromptOrigin) -> None:
    prompt = await get_prompt(orch().db, group, key)
    shown = escape(prompt) if prompt else "<i>لا يوجد برومت لهذا الخيار</i>"
    if len(shown) > 3500:
        shown = shown[:3500] + "…"
    await safe_edit_text(
        callback.message,
        f"{escape(_label(group, key))}\n\n{shown}",
        reply_markup=_prompt_actions(group, key, origin=origin),
    )


@router.callback_query(lambda q: q.data == "assistant:prompt:custom")
async def custom_prompt(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    state = await get_state(orch().db)
    prompt = str(state.get("custom_prompt") or "")
    shown = escape(prompt) if prompt else "<i>غير مفعّل</i>"
    await safe_edit_text(
        callback.message,
        f"🧩 <b>البرومت المخصص</b>\n\n{shown}",
        reply_markup=_prompt_actions("custom", "base", origin="hub", custom=True),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:open:"))
async def current_prompt(callback: CallbackQuery) -> None:
    _cancel_pending()
    parts = callback.data.split(":")
    if len(parts) != 5:
        await safe_callback_answer(callback, "مسار غير صالح")
        return
    group, origin_raw = parts[3], parts[4]
    if group not in GROUPS or origin_raw not in {"group", "hub"}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    origin: PromptOrigin = "group" if origin_raw == "group" else "hub"
    state = await get_state(orch().db)
    key = str(state[group])
    await safe_callback_answer(callback)
    await _render_prompt(callback, group, key, origin)


@router.callback_query(lambda q: q.data == "assistant:prompt:effective")
async def effective_prompt_view(callback: CallbackQuery) -> None:
    _cancel_pending()
    await safe_callback_answer(callback)
    prompt = await effective_system_prompt(orch().db)
    shown = escape(prompt) if prompt else "<i>لا يوجد برومت فعّال حاليًا.</i>"
    if len(shown) > 3500:
        shown = shown[:3500] + "…"
    await safe_edit_text(
        callback.message,
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
    parts = callback.data.split(":")
    if len(parts) != 6:
        await safe_callback_answer(callback, "مسار غير صالح")
        return
    group, key, origin_raw = parts[3], parts[4], parts[5]
    if origin_raw not in {"group", "hub"}:
        await safe_callback_answer(callback, "مسار غير صالح")
        return
    if group != "custom" and (group not in GROUPS or key not in {item.key for item in GROUPS[group]}):
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    origin: PromptOrigin = "group" if origin_raw == "group" else "hub"
    _pending_edit = PendingPromptEdit(group=group, key=key, origin=origin)
    await safe_callback_answer(callback, "أرسل البرومت الجديد")
    back_callback = _origin_back_callback(group, origin) if group != "custom" else "assistant:prompts"
    await safe_edit_text(
        callback.message,
        "✏️ <b>تعديل البرومت</b>\n\n"
        "أرسل النص الجديد كاملًا في رسالة واحدة.\n"
        "أرسل <code>-</code> لجعله فارغًا، أو /cancel للإلغاء.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="إلغاء", callback_data=f"assistant:prompt:cancel_edit:{group}:{origin}")],
            [InlineKeyboardButton(text="⬅️ رجوع", callback_data=back_callback)],
        ]),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:cancel_edit:"))
async def cancel_prompt_edit(callback: CallbackQuery) -> None:
    _cancel_pending()
    parts = callback.data.split(":")
    group = parts[3] if len(parts) > 3 else "custom"
    origin_raw = parts[4] if len(parts) > 4 else "hub"
    await safe_callback_answer(callback, "تم الإلغاء")
    if group in GROUPS and origin_raw == "group":
        await _show_group(callback, group)
    else:
        await safe_edit_text(
            callback.message,
            "📝 <b>البرومتات</b>\n\nكل ملف سلوك قابل للتعديل من هنا.",
            reply_markup=_prompts_keyboard(),
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=_origin_back_label(target.origin),
                callback_data=(
                    _origin_back_callback(target.group, target.origin)
                    if target.group != "custom"
                    else "assistant:prompts"
                ),
            )
        ]])
        await message.answer("تم إلغاء التعديل.", reply_markup=keyboard)
        return

    value = "" if text == "-" else message.text or ""
    if target.group == "custom":
        await set_state(orch().db, "custom_prompt", value)
        reopen = "assistant:prompt:custom"
    else:
        await set_prompt(orch().db, target.group, target.key, value)
        reopen = f"assistant:prompt:open:{target.group}:{target.origin}"
    _pending_edit = None

    back = (
        _origin_back_callback(target.group, target.origin)
        if target.group != "custom"
        else "assistant:prompts"
    )
    await message.answer(
        "✅ تم حفظ البرومت الجديد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 عرض البرومت", callback_data=reopen)],
            [InlineKeyboardButton(text=_origin_back_label(target.origin), callback_data=back)],
        ]),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("assistant:prompt:reset:"))
async def restore_prompt(callback: CallbackQuery) -> None:
    _cancel_pending()
    parts = callback.data.split(":")
    if len(parts) != 6:
        await safe_callback_answer(callback, "مسار غير صالح")
        return
    group, key, origin_raw = parts[3], parts[4], parts[5]
    if group not in GROUPS or origin_raw not in {"group", "hub"}:
        await safe_callback_answer(callback, "خيار غير معروف")
        return
    origin: PromptOrigin = "group" if origin_raw == "group" else "hub"
    await safe_callback_answer(callback, "تمت الاستعادة")
    await reset_prompt(orch().db, group, key)
    await _render_prompt(callback, group, key, origin)


@router.callback_query(lambda q: q.data == "assistant:reset_all")
async def reset_all_settings(callback: CallbackQuery) -> None:
    _cancel_pending()
    from pixelpilot.bot.routers.chat import clear_history

    await safe_callback_answer(callback, "تمت إعادة الإعدادات")
    await reset_all(orch().db)
    clear_history()
    await safe_edit_text(callback.message, await _settings_text(), reply_markup=_home_keyboard())
