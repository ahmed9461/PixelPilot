from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixelpilot.db import Database


@dataclass(frozen=True, slots=True)
class PromptOption:
    key: str
    label: str
    prompt: str


PERSONAS: tuple[PromptOption, ...] = (
    PromptOption("neutral", "⚪ محايد", ""),
    PromptOption("friend", "🤝 صديق يومي", "تصرّف كصديق ذكي وقريب: طبيعي، واضح، متعاون، وغير متكلّف. لا تبالغ في المجاملة، وكن عمليًا عندما يطلب المستخدم حلاً."),
    PromptOption("analyst", "🧠 عبقري تحليلي", "حلّل المسألة بدقة، فرّق بين الحقائق والافتراضات، وانتبه للتفاصيل والتناقضات. قدّم نتيجة عملية ومفهومة بدل الاستعراض."),
    PromptOption("dramatic", "❤️ حب ودراما", "اكتب وتفاعل بحس قصصي وعاطفي واضح عندما يناسب الموضوع، مع صور لغوية جميلة دون مبالغة أو ابتذال."),
    PromptOption("business", "💸 أعمال وطموح", "فكّر بعقلية تنفيذية وتجارية: ركّز على القيمة، التكلفة، المخاطر، البدائل، والخطوات القابلة للتنفيذ."),
    PromptOption("mysterious", "🌑 غامض", "استخدم أسلوبًا هادئًا وغامضًا قليلًا، بجمل واثقة ومكثفة، مع الحفاظ على الوضوح وعدم إخفاء المعلومات المهمة."),
    PromptOption("fantasy", "🧙 خيال وأساطير", "عند المهام الإبداعية استخدم خيالًا غنيًا، عوالم وصورًا سردية مميزة، مع الالتزام بطلب المستخدم وعدم تحويل الأسئلة العملية إلى قصة."),
    PromptOption("gaming", "🎮 ألعاب", "تحدث كخبير ألعاب يعرف الميكانيكيات والاستراتيجيات والمصطلحات، لكن اشرح ببساطة إذا كان المستخدم غير متخصص."),
    PromptOption("weird", "🍄 غرائبي ومميز", "اجعل الأسلوب مميزًا وغير متوقع في المهام الإبداعية، مع أفكار أصلية وترابط منطقي وعدم إنتاج هذيان أو نص عشوائي."),
    PromptOption("chaotic", "🤡 عبثي", "يمكنك استخدام فكاهة عبثية وخفة ظل عندما يناسب السياق، لكن أبقِ الإجابة مفهومة ومفيدة ولا تضحِ بالدقة."),
)

TONES: tuple[PromptOption, ...] = (
    PromptOption("balanced", "🙂 متوازن", ""),
    PromptOption("gentle", "😇 لطيف", "استخدم نبرة لطيفة وهادئة ومباشرة، بدون تصنّع أو مبالغة في المجاملة."),
    PromptOption("very_gentle", "🥰 لطيف جدًا", "اجعل النبرة دافئة وودودة جدًا، مع الحفاظ على الصراحة والدقة وعدم الإطالة بلا داعٍ."),
    PromptOption("direct", "🎯 مباشر", "اذهب مباشرة إلى المطلوب، قل الخلاصة أولًا، وقلّل المقدمات والتكرار."),
    PromptOption("formal", "🧾 رسمي", "استخدم أسلوبًا مهنيًا منظمًا ولغة سليمة، مناسبًا للمراسلات والشرح الرسمي."),
    PromptOption("funny", "😜 مضحك", "استخدم دعابة خفيفة وذكية عندما تسمح المهمة، من دون إفساد الوضوح أو تحويل كل رد إلى مزحة."),
    PromptOption("sarcastic", "😏 ساخر", "استخدم سخرية خفيفة وذكية عند ملاءمتها، وتجنب الإهانة أو التقليل من المستخدم."),
    PromptOption("bold", "😎 جريء", "استخدم نبرة واثقة وجريئة، واعرض الخيارات بوضوح، لكن لا تتظاهر باليقين عندما تكون المعلومات غير مؤكدة."),
)

REASONING: tuple[PromptOption, ...] = (
    PromptOption("auto", "✨ تلقائي", ""),
    PromptOption("fast", "⚡ سريع", "حل المطلوب بأقصر مسار موثوق، وركّز على الإجابة العملية دون توسع غير ضروري."),
    PromptOption("balanced", "🧩 متوازن", "فكّر في أهم الاحتمالات والقيود قبل الإجابة، ثم قدّم خلاصة واضحة مع سبب مختصر عند الحاجة."),
    PromptOption("deep", "🧠 عميق", "حلّل المسألة بعمق قبل الإجابة، افحص الافتراضات والبدائل والحالات الحدّية، ثم قدّم نتيجة مرتبة ومبررة بدون كشف تفكير داخلي مطوّل."),
    PromptOption("critical", "🔎 ناقد", "اختبر الادعاءات والافتراضات، وابحث عن نقاط الضعف والتناقضات والبدائل قبل تقديم النتيجة."),
)

FORMATS: tuple[PromptOption, ...] = (
    PromptOption("auto", "✨ تلقائي", ""),
    PromptOption("compact", "🪶 مختصر", "اجعل الرد مختصرًا ومباشرًا ما لم يطلب المستخدم التفصيل."),
    PromptOption("structured", "📚 منظم", "نظّم الإجابة بعناوين وفقرات أو نقاط عندما يحسن ذلك القراءة، وتجنب التقسيم المفرط."),
    PromptOption("steps", "🪜 خطوات", "عندما يكون الطلب إجرائيًا، حوّل الإجابة إلى خطوات واضحة قابلة للتنفيذ بالترتيب."),
)

LANGUAGES: tuple[PromptOption, ...] = (
    PromptOption("auto", "🌐 تلقائي", ""),
    PromptOption("ar", "🇸🇦 العربية", "استخدم العربية في إجاباتك ما لم يطلب المستخدم لغة أخرى صراحة."),
    PromptOption("en", "🇬🇧 English", "Reply in English unless the user explicitly asks for another language."),
)

GROUPS: dict[str, tuple[PromptOption, ...]] = {
    "persona": PERSONAS,
    "tone": TONES,
    "reasoning": REASONING,
    "format": FORMATS,
    "language": LANGUAGES,
}

DEFAULT_STATE: dict[str, Any] = {
    "persona": "neutral",
    "tone": "balanced",
    "reasoning": "auto",
    "format": "auto",
    "language": "auto",
    "creativity_pct": 0,
    "diversity_pct": 100,
    "response_length_pct": 100,
    "context_enabled": True,
    "context_messages": 10,
    "custom_prompt": "",
}


def _option(group: str, key: str) -> PromptOption:
    options = GROUPS[group]
    return next((item for item in options if item.key == key), options[0])


def _state_key(name: str) -> str:
    return f"assistant.state.{name}"


def _prompt_key(group: str, key: str) -> str:
    return f"assistant.prompt.{group}.{key}"


async def ensure_defaults(db: Database) -> None:
    for name, value in DEFAULT_STATE.items():
        if await db.get(_state_key(name), None) is None:
            await db.set(_state_key(name), value)


async def get_state(db: Database) -> dict[str, Any]:
    await ensure_defaults(db)
    return {
        name: await db.get(_state_key(name), default)
        for name, default in DEFAULT_STATE.items()
    }


async def set_state(db: Database, name: str, value: Any) -> None:
    if name not in DEFAULT_STATE:
        raise KeyError(name)
    await db.set(_state_key(name), value)


async def get_prompt(db: Database, group: str, key: str) -> str:
    option = _option(group, key)
    saved = await db.get(_prompt_key(group, option.key), None)
    return option.prompt if saved is None else str(saved)


async def set_prompt(db: Database, group: str, key: str, prompt: str) -> None:
    _option(group, key)
    await db.set(_prompt_key(group, key), prompt)


async def reset_prompt(db: Database, group: str, key: str) -> None:
    option = _option(group, key)
    await db.set(_prompt_key(group, option.key), option.prompt)


async def reset_all(db: Database) -> None:
    for name, value in DEFAULT_STATE.items():
        await db.set(_state_key(name), value)
    for group, options in GROUPS.items():
        for option in options:
            await db.set(_prompt_key(group, option.key), option.prompt)


async def effective_system_prompt(db: Database) -> str:
    state = await get_state(db)
    chunks: list[str] = []
    custom = str(state.get("custom_prompt") or "").strip()
    if custom:
        chunks.append(custom)
    for group in ("persona", "tone", "reasoning", "format", "language"):
        key = str(state.get(group) or DEFAULT_STATE[group])
        prompt = (await get_prompt(db, group, key)).strip()
        if prompt:
            chunks.append(prompt)
    return "\n\n".join(chunks)


async def generation_params(db: Database, *, max_output_tokens: int) -> dict[str, Any]:
    state = await get_state(db)
    creativity = max(0, min(100, int(state.get("creativity_pct") or 0)))
    diversity = max(10, min(100, int(state.get("diversity_pct") or 100)))
    length = max(10, min(100, int(state.get("response_length_pct") or 100)))

    # Preserve the proven v0.4.3 behavior until the owner changes a control:
    # temperature=0, top_p=1 and the full configured output-token allowance.
    temperature = round((creativity / 100.0) * 0.8, 2)
    top_p = round(diversity / 100.0, 2)
    minimum = min(256, max_output_tokens)
    max_tokens = int(minimum + (max_output_tokens - minimum) * (length / 100.0))
    return {
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max(minimum, min(max_output_tokens, max_tokens)),
    }


async def context_policy(db: Database, *, default_messages: int) -> tuple[bool, int]:
    state = await get_state(db)
    enabled = bool(state.get("context_enabled", True))
    count = int(state.get("context_messages") or default_messages)
    return enabled, max(1, min(40, count))
