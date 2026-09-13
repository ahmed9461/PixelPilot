# Runbook

## 1) Controller setup

```bash
git clone https://github.com/ahmed9461/PixelPilot.git
cd PixelPilot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/configure_secrets.py
```

لا تلصق التوكنات في Git أو في ملفات الوثائق. سكربت الإعداد يحفظها في `.env` فقط، وهو مستبعد من Git.

## 2) Hugging Face

1. افتح صفحة `black-forest-labs/FLUX.1-Krea-dev`.
2. وافق على الترخيص.
3. أنشئ Read-only token.
4. ضعه في `HF_TOKEN`.

## 3) Source delivery إلى Vast

الطريقة الأبسط للنسخة الأولى:

- المستودع العام جاهز: `https://github.com/ahmed9461/PixelPilot.git`.
- `PIXELPILOT_REPO_URL=https://github.com/ahmed9461/PixelPilot.git`
- `PIXELPILOT_REPO_REF=main`

بديلًا يمكن بناء template/image مخصص واستخدام `VAST_TEMPLATE_HASH`.

## 4) Preflight — قبل دفع Vast

```bash
python scripts/preflight.py
```

أو من البوت: `🧪 فحص الجاهزية`.

كل checks يجب أن تكون PASS. زر البوت يختبر Vast API أيضًا.

## 5) تشغيل Controller

```bash
python -m pixelpilot.main
```

أو:

```bash
docker compose up -d --build
```

## 6) أول Live Acceptance

1. `/start`
2. `🔎 البحث عن سيرفر`
3. افتح عرضًا واقرأ السعر.
4. `🚀 استئجار وتجهيز`.
5. لا تغلق Controller أثناء أول اختبار.
6. انتظر `✅ PixelPilot جاهز بالكامل`.
7. `🎨 إنشاء صورة` -> Natural -> 1:1 -> 1 صورة.
8. Prompt بسيط واقعي.
9. تحقق Preview.
10. `📄 إرسال الأصل`.
11. جرّب `♻️ نفس Seed`.
12. بعد الحفظ: `🗑 حذف السيرفر`.

## 7) إذا فشل Provisioning

- الافتراضي يحاول Destroy تلقائيًا.
- راجع `/workspace/pixelpilot-bootstrap.log` و`/workspace/comfyui.log` عبر SSH إذا قررت تعطيل الحذف التلقائي للتشخيص.
- لا تعتبر `Vast=running` مساويًا لـ PixelPilot Ready؛ READY لا يتم إلا من Worker health + model validation.

## 8) Restart للController

عند بدء البوت، `recover_current()` يقرأ `instance.id` من SQLite ويفحص Vast؛ إذا كان Running يحاول استعادة Worker readiness، وإذا كان Stopped يحدث المرحلة إلى STOPPED.
