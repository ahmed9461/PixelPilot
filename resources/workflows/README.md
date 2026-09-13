# Workflows

`flux_krea_api.json` هو Workflow بصيغة ComfyUI API ويُرسل مباشرة إلى `/prompt` بعد أن يعدله PixelPilot لكل طلب.

البنية المعتمدة مبنية على Workflow Krea الرسمي:

- `UNETLoader`: `flux1-krea-dev.safetensors`
- `DualCLIPLoader`: `clip_l.safetensors` + `t5xxl_fp16.safetensors`, type `flux`
- `VAELoader`: `ae.safetensors`
- `CLIPTextEncode`
- `EmptySD3LatentImage`
- `ConditioningZeroOut`
- `KSampler`: 20 steps, CFG 1.0, Euler, Simple, denoise 1.0
- `VAEDecode`
- `SaveImage`

`src/pixelpilot/workflow.py` يعمل deepcopy للملف ويعدل prompt / width / height / batch / seed / steps / filename prefix لكل Generation، حتى لا تتسرب إعدادات طلب إلى طلب آخر.
