# TODO

## Live acceptance — Qwen3-VL + Whisper

- Update `/opt/pixelpilot` to merged v0.6.0.
- Run `scripts/migrate_economy_profile.py` and verify backup created.
- Confirm marketplace still returns suitable 48GB offers <= $0.50/hour with 100GB disk.
- Restart/rerent Vast so new bootstrap runs.
- Confirm READY only after both gateway paths are available.
- Test normal Arabic conversation and follow-up context.
- Test a photo with little/no text and ask scene-specific questions.
- Test a screenshot containing text.
- Test Telegram Voice in Arabic and a normal audio file.
- Confirm follow-up to Voice uses transcript context without re-transcribing old audio.
- Test short and medium MP4 video.
- Test personality change, then verify immediate style change.
- Test live `sendMessageDraft` response streaming.
- Check `diagnose_vast.py` and record actual GPU/Whisper device.
- Confirm SQLite events contain operational metadata only, not message/transcript/media bodies.

## Optional later improvements

- Expose Whisper device/status in technical diagnostics only.
- Add a user-selectable higher/lower visual frame budget if real video tests justify it.
- Consider Qwen3-VL smaller/quantized alternate profile only as an explicit budget mode, never as silent downgrade.
- Add multiple-image album support.

