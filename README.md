# PixelPilot

PixelPilot هو بوت Telegram شخصي Owner-only يحوّل Vast.ai إلى مساعد متعدد الوسائط مؤقت عند الطلب.

## Runtime الحالي

```text
Text / Image / Video -> Qwen/Qwen3-VL-30B-A3B-Instruct-FP8
Voice / Audio        -> Whisper turbo -> Qwen3-VL
```

المعمارية الافتراضية:

```text
Telegram
  -> PixelPilot Controller
  -> public authenticated inference gateway on Vast
       -> Whisper turbo for speech transcription
       -> private localhost vLLM
            -> Qwen3-VL-30B-A3B-Instruct-FP8
```

Qwen3-VL هو المسؤول عن الفهم والحوار والرؤية والفيديو. Whisper مسؤول فقط عن تحويل الكلام المسموع إلى نص؛ النص الناتج يدخل إلى نفس سياق Qwen3-VL، لذلك أسئلة المتابعة تعمل بشكل طبيعي ولا يعاد إرسال ملف الصوت في كل Turn.

المشروع لا يولّد صورًا.

## لماذا Qwen3-VL 30B FP8؟

التجربة الحية مع Qwen2.5-Omni-7B أظهرت أن جودة الفهم العام والرؤية واتباع السياق أقل من المطلوب للاستخدام الشخصي المقصود. لذلك انتقل المشروع إلى Qwen3-VL 30B-A3B Instruct FP8 بدل الاستمرار في ترقيع موديل أصغر.

النسخة FP8 حجمها أصغر من BF16 وتستهدف فئة 48GB GPU. على Ampere مثل RTX A6000 يستطيع vLLM تشغيل FP8 كـ weight-only W8A16 باستخدام Marlin، بينما البطاقات الأحدث تستفيد من مسارات FP8 الأصلية.

المصادر الرسمية:
- Qwen3-VL FP8: https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Instruct-FP8
- vLLM: https://docs.vllm.ai/
- Whisper: https://github.com/openai/whisper
- Vast.ai: https://docs.vast.ai/

## القدرات

- محادثة نصية مع سياق RAM-only.
- فهم صور فعلي عبر Qwen3-VL.
- فهم فيديو عبر Qwen3-VL مع sampling مضبوط للإطارات.
- Telegram Voice والملفات الصوتية عبر Whisper turbo.
- Streaming حي للرد عبر Telegram message drafts.
- Rich Messages وRTL وأزرار Telegram الحديثة.
- شخصيات/سمات/استدلال/تنسيق/لغة قابلة للتعديل من داخل البوت.
- كل Prompt مستخدم في السلوك قابل للعرض والاستبدال والاستعادة من Telegram.
- Rent / Start / Stop / Destroy لسيرفر Vast.
- بحث سوق حي مع سقف استئجار صلب `$0.50/hour`.
- عداد وقت وتكلفة تقديرية بالثانية.
- Cost Guard وPreflight واستعادة حالة الـInstance بعد Restart.

## السلوك والبرومتات

الوضع المحايد الافتراضي لا يضيف Prompt سلوكي. عندما يختار المالك شخصية أو سمة أو استدلال أو تنسيق أو لغة، PixelPilot يجمع فقط الأجزاء المرئية والقابلة للتعديل داخل **إعدادات المساعد** في System message واحدة.

لا توجد System/Developer instructions مخفية خارج ما يستطيع المالك رؤيته وتعديله. البرومت المخصص له حالة تشغيل/إيقاف مستقلة وواضحة داخل البوت.

تغيير ملف السلوك يبدأ سياق RAM جديد حتى لا تؤثر ردود الشخصية السابقة على الشخصية الجديدة. وعند اختيار **شخصية** جديدة تحديدًا، يعيد PixelPilot السمة والاستدلال والتنسيق إلى الوضع التلقائي ويوقف البرومت المخصص دون حذفه، حتى لا تطغى طبقة قديمة على الشخصية المختارة.

## إعدادات الأسلوب

الإعداد الافتراضي للمحادثة اليومية هو:
- Creativity: `30%` → `temperature=0.3`
- Diversity: `80%` → `top_p=0.8`
- Top-K: `20`
- Repetition penalty: `1.0`

تم خفض الإبداع الافتراضي عن إعداد Qwen3-VL المنشور لأن الاستخدام الحي كمساعد يومي أظهر ميلًا زائدًا للفلسفة والخيال عند 70%. يمكن رفع الإبداع يدويًا من Telegram للقصص والكتابة الإبداعية.

## الصوت

الصوت لا يذهب إلى Qwen3-VL كـ audio tokens. التدفق:

1. Telegram يرسل Voice/Audio إلى Controller.
2. الملف يرسل إلى Whisper turbo على نفس Vast instance.
3. Whisper يعيد transcript.
4. Controller يضع transcript بدل الملف الصوتي في رسالة المستخدم.
5. Qwen3-VL يفهم transcript ضمن نفس الشخصية والسياق.
6. history يحتفظ بالنص فقط، وليس ملف الصوت/base64.

هذا يمنع تضخم السياق وإعادة معالجة نفس الصوت في كل رسالة متابعة.

## الفيديو

الفيديو يرسل كـ `video_url` فعلي إلى Qwen3-VL. vLLM مضبوط افتراضيًا على:
- فيديو واحد لكل Prompt.
- 24 إطارًا sampled.
- frame recovery للفيديوهات غير المثالية.
- Context بطول 16384.

عند إرسال فيديو جديد لا يتم إرفاق History القديم بذلك الطلب حتى لا يستهلك الفيديو + المحادثة السابقة نافذة السياق قبل بدء الإجابة.

## العتاد الافتراضي

`.env.example` يبدأ بسياسة:

- GPU VRAM: `48 GB` أو أكثر.
- Disk: `100 GB`.
- Model context: `16384`.
- Qwen3-VL checkpoint: FP8.
- vLLM GPU utilization: `0.82` لترك headroom لـ Whisper.
- Whisper device: `auto`؛ يستخدم CUDA إذا وجد ذاكرة حرة كافية وإلا يعود إلى CPU.
- سقف السعر: `$0.50/hour`.

بطاقات مثل RTX A6000 يمكن أن تشغل الملف الحالي، مع ملاحظة أن FP8 على Ampere يستخدم weight-only Marlin وليس FP8 compute الأصلي.

## المنافذ

- `8190`: PixelPilot inference gateway — هو المنفذ الوحيد المعروض للعامة ومحمّي Bearer token.
- `8191`: vLLM داخلي على `127.0.0.1` فقط.

الـGateway يقدّم:
- `/health`
- `/v1/models`
- `/v1/chat/completions`
- `/v1/audio/transcriptions`

## ترقية تثبيت موجود

بعد Pull للإصدار الجديد:

```bash
cd /opt/pixelpilot
git pull --ff-only origin main
/opt/pixelpilot/.venv/bin/python -m pip install -e .
/opt/pixelpilot/.venv/bin/python scripts/migrate_economy_profile.py
systemctl restart pixelpilot.service
```

سكريبت migration:
- يأخذ Backup من `.env`.
- لا يغيّر Telegram token أو Vast API key أو HF token.
- ينقل Profile التشغيل إلى Qwen3-VL + Whisper.

أي Vast instance يعمل بالـruntime القديم يحتاج **Stop ثم Start** بعد تحديث Controller، أو حذفه واستئجار Instance جديد، حتى يعيد `onstart` جلب `main` وتشغيل bootstrap الجديد.

## الإعداد الأول

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/configure_secrets.py
python scripts/preflight.py
python -m pixelpilot.main
```

القيم المطلوبة:
- `TELEGRAM_BOT_TOKEN`
- `OWNER_TELEGRAM_ID`
- `VAST_API_KEY`
- `PIXELPILOT_REPO_URL` أو `VAST_TEMPLATE_HASH`

`HF_TOKEN` اختياري.

## الخصوصية والأمان

- `VAST_API_KEY` يبقى على Controller.
- الـGPU instance يأخذ inference token عشوائي وHF token فقط إذا تم ضبطه.
- vLLM لا يتعرض مباشرة للإنترنت؛ الـGateway فقط هو public.
- رسائل المستخدم ووسائطه لا تُكتب في SQLite.
- Conversation history في RAM فقط.
- حذف Vast instance يمسح الـruntime والكاش على السيرفر المؤقت.
- لا تضع `.env` أو أي Token في Git.

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
