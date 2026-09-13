# Security

## Secrets

- لا Tokens في Git.
- `VAST_API_KEY` يبقى على Controller فقط.
- `HF_TOKEN` يجب أن يكون Read-only، ويُرسل للـInstance وقت Rent فقط لتنزيل gated weights.
- Worker token عشوائي جديد لكل Instance.
- Controller لا يسجل Worker/HF/Vast tokens في events.

## Network

- ComfyUI: `127.0.0.1:8188` فقط.
- Worker: `127.0.0.1:18190` فقط.
- Vast base-image Caddy/Portal: proxy خارجي على 8190 مع `OPEN_BUTTON_TOKEN`.
- Controller يستخدم HTTPS للـWorker افتراضيًا. `WORKER_VERIFY_TLS=false` افتراضيًا لأن الوصول عبر IP/mapped-port قد لا يملك certificate قابلًا للتحقق باسم المضيف؛ غيّره إلى true فقط إذا كانت بيئتك تقدم شهادة يمكن التحقق منها.

## Telegram

- Global Owner-only middleware.
- غير المالك لا يتلقى ردًا.
- Destroy يحتاج Confirmation.
- Rent يحتاج Review/Confirmation للسعر.

## Cost safety

- Hard max price في Search/Controller.
- Auto-Destroy عند provisioning failure.
- Idle warning.
- Idle Auto-Destroy opt-in فقط.

## Provider trust

أي GPU cloud host يشغّل الكود على جهاز لا تملكه. استخدم Read-only HF token محدود الصلاحية، ولا تمرر أسرارًا غير ضرورية للـInstance.
