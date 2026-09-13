# TODO — المتبقي الحقيقي بعد اكتمال البناء المحلي

## P0 — متطلبات خارجية لأول تشغيل حي

- [x] إنشاء Telegram bot (التوكن موجود لدى المستخدم؛ لا يُحفظ في Git).
- [x] Telegram User ID معروف للمستخدم؛ سيُدخل محليًا في `.env` ولا يُحفظ في المستودع.
- [x] إنشاء Vast API key (القيمة سرية لدى المستخدم).
- [ ] التأكد من وجود رصيد كافٍ لأول جلسة Live Acceptance.
- [x] قبول ترخيص FLUX.1 Krea في Hugging Face.
- [x] إنشاء HF Read token (القيمة سرية لدى المستخدم).
- [x] نشر المستودع العام `ahmed9461/PixelPilot` ليكون Vast قادرًا على clone بدون Git credentials.
- [ ] تشغيل `python scripts/configure_secrets.py` على جهاز/خادم Controller.
- [ ] تشغيل `python scripts/preflight.py` حتى تكون كل النتائج PASS.

## P0 — Live Acceptance

- [ ] Search حقيقي من البوت.
- [ ] Rent عرض 48GB مناسب.
- [ ] تحقق أن Caddy Worker endpoint يصل من Controller.
- [ ] تحقق تنزيل الملفات الأربعة.
- [ ] تحقق `/health`: `comfy_ready=true`, `models_ready=true`.
- [ ] توليد صورة واحدة 1024×1024.
- [ ] استلام Preview + Original في Telegram.
- [ ] Re-run بنفس Seed.
- [ ] Destroy من البوت والتحقق أن الـInstance اختفى.

## P1 — بعد قياس الجلسة الحقيقية

- [x] تثبيت `COMFYUI_REF=v0.35.0` بدل تتبع `master` لتحسين reproducibility.
- [ ] قياس هل 24GB/32GB مع quantization يستحق إضافة Economy profile.
- [ ] قياس download time؛ إذا كان cold start طويلًا أضف optional persistent volume/cache profile.

## P2 — Features لاحقة وليست مطلوبة للنسخة الأولى

- [ ] LoRA.
- [ ] Upscale.
- [ ] Image-to-image.
- [ ] HiDream/Qwen model profiles.
- [ ] External object storage لحفظ Originals بعد Destroy.
