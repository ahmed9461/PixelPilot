# Architecture Decision Log

## ADR-001 — Telegram هو الواجهة اليومية
**الحالة:** Accepted

الاستخدام الأساسي من الجوال؛ ComfyUI backend فقط.

## ADR-002 — Controller خارج Vast
**الحالة:** Accepted

لو عاش البوت داخل الـInstance فلن يستطيع إنشاء Instance جديد بعد Destroy.

## ADR-003 — Vast SDK الرسمي
**الحالة:** Accepted

يستخدم SDK للبحث والإنشاء وLifecycle بدل REST hard-code. `template_hash` هو المعرف الصحيح لإنشاء instance من template.

## ADR-004 — Destroy هو الوضع الاقتصادي المفضل
**الحالة:** Accepted

Stop يبقي التخزين مدفوعًا؛ Destroy يمسح البيانات، لذلك bootstrap idempotent قدر الإمكان.

## ADR-005 — Workflow API رسمي البنية
**الحالة:** Accepted

تم اعتماد Workflow API مبني من عقد وإعدادات Workflow Krea الرسمي بدل تحويلات UI غير الموثوقة.

## ADR-006 — 48GB VRAM كبداية
**الحالة:** Accepted / قابل للمراجعة بعد Live Test

الهدف هو تجربة full weights + FP16 text encoder بأقل صراع مع offload/quantization.

## ADR-007 — ComfyUI localhost + Worker خلف Caddy
**الحالة:** Accepted

ComfyUI لا يُفتح خارجيًا. Worker الداخلي على 18190، وVast base-image Caddy يعرض proxy port 8190 مع OPEN_BUTTON_TOKEN/TLS.

## ADR-008 — Tokens per-instance
**الحالة:** Accepted

يولد Controller Worker token عشوائي لكل Rent. Vast API key لا ينتقل إلى الـGPU. HF token read-only فقط هو المطلوب للتنزيل.

## ADR-009 — Auto rollback عند فشل provisioning
**الحالة:** Accepted

الافتراضي `true` لمنع استمرار GPU مدفوع إذا فشل الإعداد قبل Ready.

## ADR-010 — Idle Auto-Destroy opt-in
**الحالة:** Accepted

التنبيه مفعّل افتراضيًا، أما الحذف التلقائي للخمول = 0 افتراضيًا حتى لا نفقد صورًا بدون قرار صريح.
