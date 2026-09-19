# Test Plan

## Automated

CI runs Python 3.12 compileall + pytest.

Regression coverage must include:
- Qwen3-VL 30B FP8 default settings.
- 48GB minimum VRAM, 100GB disk and $0.50/hour cap.
- safe `.env` migration without touching secrets.
- public gateway / private vLLM environment propagation.
- exact text/image/video message construction.
- Whisper transcription client request shape.
- audio-to-transcript path before Qwen history.
- streamed and non-streamed chat payloads.
- assistant behavior profiles and editable prompt migrations.
- Telegram settings navigation and Rich Message builders.
- Vast lifecycle/recovery and live billing.
- marketplace refresh and offer policy.

## Live acceptance

On a real rented 48GB GPU:
1. Provision from a clean or restarted instance.
2. Confirm Qwen3-VL model appears in `/v1/models`.
3. Confirm gateway `/health` only succeeds after Whisper is loaded.
4. Test Arabic text.
5. Test a non-text-centric image and follow-up question.
6. Test screenshot/OCR behavior.
7. Test Voice/Audio transcription and follow-up.
8. Test video understanding.
9. Test behavior/personality profile effect.
10. Test streaming draft smoothness.
11. Check VRAM and Whisper selected device.
12. Stop/start and verify runtime recovery without redownloading unnecessary assets.
