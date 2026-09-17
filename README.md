# PixelPilot

PixelPilot هو بوت Telegram شخصي Owner-only يحوّل Vast.ai إلى مساعد متعدد الوسائط عند الطلب باستخدام `Qwen/Qwen3-Omni-30B-A3B-Instruct`.

```text
Telegram -> PixelPilot Controller -> Vast.ai -> vLLM -> Qwen3-Omni
```

المشروع لا يولّد صورًا. وظيفته الحالية هي **المحادثة النصية وفهم الصور وفهم الصوت**. لا يوجد GPU ثابت: تبحث من البوت عن عرض مناسب، تستأجره، PixelPilot يجهز vLLM والموديل تلقائيًا، ثم تحذف الـInstance عندما تنتهي.

## مبدأ مهم: لا System Prompt

PixelPilot لا يضيف `system` أو `developer` message، ولا يترجم كلام المستخدم، ولا يعيد صياغته، ولا يفرض لغة على الموديل.

- النص يمر كما كتبه المستخدم.
- الصورة تمر للموديل كمدخل بصري فعلي، وليس OCR فقط.
- Voice/Audio يمر للموديل كمدخل صوتي فعلي.
- Caption المرفق بالصورة/الصوت يمر كما هو.
- إذا أُرسلت صورة أو صوت بلا Caption، لا يخترع PixelPilot تعليمات مخفية من عنده.

المحادثة الحالية تحفظ في RAM فقط على Controller كي تعمل أسئلة المتابعة. الأمر `/new` أو زر **محادثة جديدة** يمسح السياق. محتوى المحادثة لا يُكتب إلى SQLite؛ سجل الأحداث يحفظ metadata تشغيلية فقط.

## ما يعمل

- Owner-only Telegram bot.
- البحث عن عروض Vast حسب VRAM والسعر والموثوقية والقرص والشبكة.
- Rent / Start / Stop / Destroy وإعادة استعادة حالة الـInstance بعد Restart.
- Bootstrap تلقائي لـ vLLM وQwen3-Omni على السيرفر المؤقت.
- Endpoint محمي بمفتاح عشوائي خاص بكل Instance.
- رسائل نصية عربية/إنجليزية وغيرها.
- الصور وملفات الصور.
- Telegram Voice والملفات الصوتية.
- سياق محادثة قصير في الذاكرة فقط، مع `/new` للمسح.
- Preflight قبل الاستئجار.
- Cost Guard للتنبيه على GPU الخامل؛ الحذف التلقائي اختياري ومغلق افتراضيًا.
- SQLite لحالة السيرفر والأحداث التشغيلية فقط.
- اختبارات تمنع إعادة إدخال System Prompt بالخطأ.

## الموديل

الافتراضي:

```text
Qwen/Qwen3-Omni-30B-A3B-Instruct
```

Qwen3-Omni يدعم مدخلات نص وصورة وصوت وفيديو. PixelPilot يستخدم حاليًا النص والصورة والصوت ويطلب مخرجات نصية فقط.

المصادر الرسمية:

- Qwen3-Omni: https://github.com/QwenLM/Qwen3-Omni
- Model: https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct
- vLLM serving: https://docs.vllm.ai/
- Vast.ai: https://docs.vast.ai/

## العتاد الافتراضي

الملف `.env.example` يبدأ بسياسة محافظة نسبيًا:

- GPU VRAM: `80 GB` أو أكثر.
- Disk: `150 GB`.
- Model context: `32768`.
- BF16 على GPU واحد افتراضيًا.

الموديل على Hugging Face حجمه يقارب 70 GB، لذلك القرص وVRAM مضبوطان أعلى من المشاريع الصغيرة. يمكن تعديل الإعدادات لاحقًا حسب الـGPU الفعلي.

## الإعداد الأول

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/configure_secrets.py
python scripts/preflight.py
python -m pixelpilot.main
```

المطلوب في `.env` على الأقل:

- `TELEGRAM_BOT_TOKEN`
- `OWNER_TELEGRAM_ID`
- `VAST_API_KEY`
- `PIXELPILOT_REPO_URL` أو `VAST_TEMPLATE_HASH`

`HF_TOKEN` اختياري لأن الموديل عام.

## التشغيل عبر Docker

```bash
docker compose up -d --build
docker compose logs -f
```

قاعدة البيانات تحفظ في `./data/pixelpilot.sqlite3`.

## تدفق الاستخدام

1. `/start`
2. `🧪 فحص الجاهزية`
3. `🔎 البحث عن سيرفر`
4. مراجعة السعر والـGPU
5. `🚀 استئجار وتجهيز`
6. انتظار رسالة جاهزية Qwen3-Omni
7. إرسال نص أو صورة أو Voice/Audio مباشرة للبوت
8. `/new` عند الرغبة في بدء سياق جديد
9. `🗑 حذف السيرفر` عند الانتهاء لإيقاف تكلفة الـInstance

## الأمان والخصوصية

- `VAST_API_KEY` يبقى على Controller ولا يُرسل إلى GPU instance.
- الـInstance يأخذ token عشوائي للـInference API و`HF_TOKEN` فقط إن كان مضبوطًا.
- vLLM API يتطلب Bearer token عشوائي خاص بالـInstance.
- لا تضع `.env` أو أي token في Git.
- لا يوجد System Prompt مخفي داخل PixelPilot.
- رسائل المستخدم وصوره وصوته لا تُحفظ في SQLite.
- ذاكرة المحادثة الحالية RAM-only وتختفي عند `/new` أو Restart للـController.
- حذف Vast instance يمسح كاش الموديل والبيانات الموجودة على ذلك السيرفر المؤقت.

## ذاكرة المشروع

- `docs/PROJECT_MEMORY.md`
- `docs/PROGRESS.md`
- `docs/TODO.md`
- `docs/DECISIONS.md`
- `docs/ARCHITECTURE.md`
- `docs/RUNBOOK.md`
- `docs/SECURITY.md`
- `docs/TEST_PLAN.md`
- `docs/FINAL_BUILD_REPORT.md`
