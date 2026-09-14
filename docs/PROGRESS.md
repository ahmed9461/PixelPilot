# Progress

آخر تحديث: 2026-09-14

## Phase 0 — Discovery ✅

- [x] اختيار FLUX.1 Krea [dev].
- [x] اختيار Vast.ai للتشغيل المؤقت.
- [x] Telegram كواجهة يومية.
- [x] Destroy كوضع اقتصادي أساسي.

## Phase 1 — Controller Foundation ✅

- [x] Settings + `.env.example`.
- [x] SQLite state/events/generations.
- [x] Owner-only middleware.
- [x] Main menu.
- [x] Vast SDK gateway.
- [x] Offer filters + cache + details + rent confirmation.
- [x] Start / Stop / Destroy.
- [x] State recovery after controller restart.

## Phase 2 — Provisioning ✅ (code-complete)

- [x] Krea model manifest full profile.
- [x] Download integrity minimum-size checks.
- [x] Vast random Worker token per Instance.
- [x] Correct `template_hash` support.
- [x] Direct repo clone/onstart mode.
- [x] Vast port mapping parser.
- [x] Caddy/Portal plan: external 8190 -> worker localhost 18190.
- [x] ComfyUI localhost only.
- [x] Bootstrap: ComfyUI checkout/install -> model download -> Comfy start -> Worker start.
- [x] Health loop + READY only after Worker validates model presence.
- [x] Auto-Destroy rollback on provisioning failure.

## Phase 3 — Generation ✅ (code-complete)

- [x] FLUX Krea API workflow JSON.
- [x] Worker `/jobs`, `/jobs/{id}`, `/images`.
- [x] Controller WorkerClient.
- [x] Telegram preset selection.
- [x] Aspect ratios 1:1 / 4:5 / 3:2 / 16:9 / 9:16.
- [x] Batch 1/2/4 (bounded by config).
- [x] Random Seed and stored Seed.
- [x] Re-run same Seed / new Seed.
- [x] Preview image + Original Document.
- [x] Generation history in SQLite.
- [x] One generation at a time guard.

## Phase 4 — Reliability / Cost ✅ (software)

- [x] Preflight button.
- [x] Hard price ceiling.
- [x] Minimum VRAM/reliability/disk/network/verified filters.
- [x] Provision timeout.
- [x] Cost Guard idle warning.
- [x] Optional idle Auto-Destroy.
- [x] Worker/Comfy separation and token handling.
- [x] CI workflow.
- [x] Docker controller deployment.
- [x] Secure interactive `.env` configurator (secrets not echoed / `.env` gitignored).

## Tests ✅

- 31 tests passing before the first live preflight; CI is enabled for every push.
- Includes fake end-to-end lifecycle: search -> rent -> ready -> generate -> download -> stop -> start -> destroy.
- Includes Worker FastAPI authentication/job/image test.
- Added regression coverage for Vast `gpu_ram` query units after the first live preflight exposed a `48000` vs `48` mismatch.

## Live acceptance ⏳

Software البناء مكتمل محليًا. المستخدم أكد إنشاء Telegram Bot Token وVast API Key وHF Token وقبول ترخيص Krea؛ القيم نفسها لا تُحفظ في المستودع.

- [x] نشر PixelPilot إلى GitHub العام (`ahmed9461/PixelPilot`).
- [x] إدخال الأسرار محليًا عبر `python scripts/configure_secrets.py`.
- [x] تشغيل أول `python scripts/preflight.py`: Telegram/Vast/HF/Git/workflow/manifest/policy كلها PASS.
- [x] اكتشاف وإصلاح Bug في Vast VRAM query (`gpu_ram>=48` بدل `gpu_ram>=48000`).
- [ ] سحب الإصلاح محليًا وإعادة preflight للتأكد من ظهور عروض مطابقة.
- [ ] استئجار GPU حقيقي وتشغيل Live Acceptance مرة واحدة.
- [ ] قياس زمن cold start والـVRAM الفعلي ثم تعديل policy إن لزم.
