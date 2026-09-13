# PixelPilot

PixelPilot هو بوت Telegram شخصي Owner-only يحوّل Vast.ai إلى استوديو صور GPU عند الطلب:

```text
Telegram -> PixelPilot Controller -> Vast.ai -> PixelPilot Worker -> ComfyUI -> FLUX.1 Krea Dev
```

الفكرة الأساسية: لا يوجد GPU ثابت. تبحث من البوت عن عرض مناسب، تراجعه، تستأجره، PixelPilot يجهزه تلقائيًا، يولد الصور، ثم تستطيع Destroy بالكامل عند الانتهاء.

## ما يعمل في النسخة الحالية

- Owner-only Telegram bot.
- البحث عن عروض Vast حسب VRAM / السعر / Reliability / Disk / Network / verified host.
- مراجعة العرض والسعر قبل Rent.
- Rent عبر Vast Python SDK الرسمي.
- Bootstrap تلقائي لـ ComfyUI + ملفات FLUX.1 Krea الكاملة.
- Worker خلف Vast base-image Caddy؛ ComfyUI نفسه localhost فقط.
- انتظار تلقائي للحالات: `RENTING -> BOOTING -> PROVISIONING -> READY`.
- Rollback/Destroy تلقائي اختياري عند فشل provisioning.
- Workflow API فعلي لـ FLUX.1 Krea.
- توليد من Telegram: preset + ratio + batch + prompt.
- نسب جاهزة: 1:1 / 4:5 / 3:2 / 16:9 / 9:16.
- إعادة بنفس Seed أو Seed جديد.
- إرسال Preview وصورة الأصل كـDocument.
- Stop / Start / Destroy.
- Preflight قبل الاستئجار.
- Cost Guard للتنبيه على الخمول؛ Auto-Destroy اختياري ومغلق افتراضيًا.
- استعادة حالة الـInstance بعد Restart للبوت.
- SQLite للأحداث والحالة وسجل التوليد.
- اختبارات Unit/Integration بدون استئجار GPU حقيقي.

## الإعداد الأول

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/configure_secrets.py
python scripts/preflight.py
python -m pixelpilot.main
```

`configure_secrets.py` يطلب القيم الحساسة بدون إظهار التوكنات على الشاشة، ويكتبها فقط إلى `.env` المستبعد من Git. لا تضع الأسرار في `.env.example`.

المطلوب في `.env` على الأقل:

- `TELEGRAM_BOT_TOKEN`
- `OWNER_TELEGRAM_ID`
- `VAST_API_KEY`
- `HF_TOKEN` (Read-only وبعد قبول ترخيص Krea)
- `PIXELPILOT_REPO_URL` بعد نشر هذا المستودع في Git server يمكن لـ Vast الوصول إليه، أو استخدم `VAST_TEMPLATE_HASH` لقالب يحتوي المشروع/الـbootstrap.

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
4. افتح عرضًا وراجع السعر
5. `🚀 استئجار وتجهيز`
6. انتظر `✅ PixelPilot جاهز بالكامل`
7. `🎨 إنشاء صورة`
8. احفظ الصور المهمة خارج Vast
9. `🗑 حذف السيرفر`

## الأمان

- `VAST_API_KEY` لا يغادر خادم Controller.
- GPU instance يأخذ فقط `HF_TOKEN` read-only + token عشوائي خاص بالـWorker.
- لا تضع `.env` أو أي token في Git.
- ComfyUI يستمع على `127.0.0.1` فقط.
- Worker يستمع داخليًا فقط ويُمرَّر عبر Caddy في Vast base image.
- لا تعتمد على بيانات الـInstance كنسخة دائمة؛ Destroy يمسحها نهائيًا.

## المصادر الفنية المستخدمة في التصميم

- Vast.ai docs: https://docs.vast.ai/
- Vast Python SDK: https://docs.vast.ai/sdk/python/
- Vast networking/ports: https://docs.vast.ai/guides/instances/connect/networking
- ComfyUI server API: https://docs.comfy.org/development/comfyui-server/comms_routes
- ComfyUI FLUX.1 Krea tutorial: https://docs.comfy.org/tutorials/flux/flux1-krea-dev
- FLUX.1 Krea model: https://huggingface.co/black-forest-labs/FLUX.1-Krea-dev

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
