# Architecture

```text
Telegram (Owner only)
       |
       v
PixelPilot Controller (persistent cheap host)
       |
       +-- SQLite
       |    |- instance state
       |    |- offer cache
       |    |- events
       |    `- generation metadata
       |
       +-- VastSdkGateway
       |    |- search offers
       |    |- rent
       |    |- show/start/stop/destroy
       |    `- mapped-port discovery
       |
       +-- Orchestrator
       |    |- lifecycle state machine
       |    |- provisioning readiness
       |    |- rollback
       |    |- generation serialization
       |    `- cost activity tracking
       |
       `-- WorkerClient (Bearer token)
                |
                | HTTPS via Vast Caddy/Portal
                v
Vast GPU Instance
  |
  +-- Caddy / Instance Portal :8190
  |      `-- auth OPEN_BUTTON_TOKEN
  |             |
  |             v
  +-- PixelPilot Worker 127.0.0.1:18190
  |      |- /health
  |      |- /jobs
  |      |- /jobs/{prompt_id}
  |      `- /images
  |             |
  |             v
  `-- ComfyUI 127.0.0.1:8188
         |- /prompt
         |- /history/{id}
         |- /models/{folder}
         `- /view
                |
                v
          FLUX.1 Krea Dev
```

## State machine

```text
NONE
 -> RENTING
 -> BOOTING
 -> PROVISIONING
 -> READY
 -> STOPPING -> STOPPED -> BOOTING ...
 -> DESTROYING -> NONE

Any provisioning failure -> ERROR -> optional automatic DESTROY -> NONE
```

## Storage policy

Controller SQLite دائم. Vast local disk مؤقت ويُعتبر disposable. Image metadata يبقى في SQLite، لكن Original bytes تعتمد على بقاء الـInstance؛ لذلك يجب تنزيل الصور المهمة قبل Destroy أو إضافة object storage لاحقًا.
