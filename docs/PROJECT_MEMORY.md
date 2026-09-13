# PixelPilot — Project Memory

> المرجع الأول عند استكمال المشروع في أي جلسة لاحقة. حدّث هذا الملف فقط عند تغير قرار ثابت أو تدفق أساسي.

## الهدف

بوت Telegram شخصي Owner-only يستخدم GPU مؤقتًا من Vast.ai لإنشاء صور طبيعية عالية الجودة بـ FLUX.1 Krea. لا يوجد GPU ثابت: Search -> Review -> Rent -> Auto Provision -> Generate -> Destroy.

## القرارات الحالية

- اسم المستودع: `PixelPilot`.
- GitHub remote العام: `https://github.com/ahmed9461/PixelPilot.git`.
- الواجهة اليومية: Telegram Bot.
- Controller يعيش على استضافة صغيرة دائمة خارج Vast.
- GPU Cloud: Vast.ai.
- Image backend: ComfyUI self-hosted API.
- الموديل الأول: `black-forest-labs/FLUX.1-Krea-dev` full weights.
- Target profile الأول: GPU بذاكرة 48GB، T5 FP16، disk 100GB.
- الاستخدام: شخصي/هواية.
- الأولوية: photorealism / natural details / premium aesthetics.
- Cost mode المفضل: Destroy عند الانتهاء؛ Stop متاح لكنه يبقي رسوم التخزين.
- Owner-only: أي Telegram ID غير المالك يُهمل.
- الأسرار في env فقط؛ لا Tokens في Git.
- Vast API key يبقى على Controller ولا يرسل للـGPU.
- HF token Read-only يمر للـInstance فقط وقت التشغيل لتنزيل Krea.
- ComfyUI لا يُكشف للعالم؛ localhost فقط.
- Worker خلف Vast base-image Caddy/portal على proxy port 8190 إلى localhost:18190.
- Vast SDK parameter الصحيح للقالب هو `template_hash` / `VAST_TEMPLATE_HASH`، وليس numeric template ID.
- Direct deployment لا يحتاج Template إذا كان `PIXELPILOT_REPO_URL` متاحًا للـInstance.
- Auto-Destroy عند فشل provisioning مفعّل افتراضيًا.
- Idle Auto-Destroy متاح لكنه Disabled افتراضيًا (`0`) لمنع حذف غير مقصود.

## Workflow Krea المعتمد

الـAPI workflow يطابق workflow الرسمي المبسط:

- `UNETLoader`: `flux1-krea-dev.safetensors`
- `DualCLIPLoader`: `clip_l.safetensors` + `t5xxl_fp16.safetensors`, type `flux`
- `VAELoader`: `ae.safetensors`
- `CLIPTextEncode`
- `EmptySD3LatentImage`
- `ConditioningZeroOut`
- `KSampler`: 20 steps / CFG 1.0 / Euler / simple / denoise 1.0
- `VAEDecode`
- `SaveImage`

## ملفات الموديل

- `diffusion_models/flux1-krea-dev.safetensors`
- `text_encoders/clip_l.safetensors`
- `text_encoders/t5xxl_fp16.safetensors`
- `vae/ae.safetensors`

## تدفق الاستخدام

1. `/start`
2. `🧪 فحص الجاهزية`
3. `🔎 البحث عن سيرفر`
4. عرض التفاصيل والسعر
5. `🚀 استئجار وتجهيز`
6. Controller يولد Worker token عشوائيًا ويستأجر Vast.
7. onstart يجلب PixelPilot، ثم `bootstrap_vast.sh`.
8. Bootstrap يجهز ComfyUI وينزل الموديلات ويشغل Worker.
9. Controller يقرأ public IP + mapped port ويراقب `/health`.
10. لا يرسل READY إلا إذا ComfyUI + الموديلات Ready.
11. Telegram generation flow.
12. الصور ترجع Preview؛ Original متاح كـDocument ما دام الـInstance موجودًا.
13. `🗑 Destroy` عند الانتهاء.

## ملفات الحالة

- `docs/PROGRESS.md`: ما تم فعليًا.
- `docs/TODO.md`: المتبقي الحقيقي فقط.
- `docs/DECISIONS.md`: ADRs.
- `docs/FINAL_BUILD_REPORT.md`: تقرير البناء الحالي.

## الحالة الحالية

- Local MVP code-complete.
- 31/31 automated tests passing.
- Python compile check PASS.
- GitHub source published.
- External credentials created by the user but intentionally not stored in Git.
- Remaining gate: local secret injection + Preflight + one paid Vast Live Acceptance.
