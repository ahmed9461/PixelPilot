from fastapi.testclient import TestClient

import pixelpilot.worker as worker


class FakeComfy:
    async def is_ready(self):
        return True

    async def models(self, folder):
        mapping = {
            "diffusion_models": ["flux1-krea-dev.safetensors"],
            "text_encoders": ["clip_l.safetensors", "t5xxl_fp16.safetensors"],
            "vae": ["ae.safetensors"],
        }
        return mapping[folder]

    async def submit(self, workflow, client_id):
        assert workflow["4"]["inputs"]["text"] == "A natural photo"
        assert workflow["10"]["class_type"] == "FluxGuidance"
        assert workflow["10"]["inputs"]["guidance"] == 4.5
        assert workflow["7"]["inputs"]["positive"] == ["10", 0]
        return "pid-1"

    async def job_status(self, prompt_id):
        return {"status": "completed", "images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}

    async def download_image(self, filename, subfolder, image_type):
        return b"PNG"

    async def system_stats(self):
        return {"devices": []}


def test_worker_auth_health_and_generation(monkeypatch):
    monkeypatch.setattr(worker, "WORKER_TOKEN", "secret")
    monkeypatch.setattr(worker, "comfy", FakeComfy())
    client = TestClient(worker.app)

    assert client.get("/health").status_code == 401
    headers = {"Authorization": "Bearer secret"}
    health = client.get("/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["models_ready"] is True

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "prompt": "A natural photo",
            "width": 1024,
            "height": 1024,
            "seed": 1,
            "steps": 28,
            "batch_size": 1,
            "preset": "raw",
            "quality_profile": "krea_quality",
            "filename_prefix": "PixelPilot/test",
        },
    )
    assert response.status_code == 200
    assert response.json()["prompt_id"] == "pid-1"
    status = client.get("/jobs/pid-1", headers=headers)
    assert status.json()["status"] == "completed"
    image = client.get("/images?filename=x.png", headers=headers)
    assert image.content == b"PNG"
