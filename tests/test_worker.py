from fastapi.testclient import TestClient

import pixelpilot.worker as worker


class FakeComfy:
    async def is_ready(self):
        return True

    async def models(self, folder):
        mapping = {
            "diffusion_models": ["flux2_dev_fp8mixed.safetensors"],
            "text_encoders": ["mistral_3_small_flux2_fp8.safetensors"],
            "vae": ["flux2-vae.safetensors"],
        }
        return mapping[folder]

    async def submit(self, workflow, client_id):
        assert workflow["4"]["inputs"]["text"] == "A natural photo"
        assert workflow["5"]["class_type"] == "FluxGuidance"
        assert workflow["5"]["inputs"]["guidance"] == 4.0
        assert workflow["7"]["inputs"]["noise_seed"] == 1
        assert workflow["9"]["inputs"]["steps"] == 50
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
            "steps": 50,
            "batch_size": 1,
            "preset": "raw",
            "quality_profile": "flux2_quality",
            "filename_prefix": "PixelPilot/test",
        },
    )
    assert response.status_code == 200
    assert response.json()["prompt_id"] == "pid-1"
    status = client.get("/jobs/pid-1", headers=headers)
    assert status.json()["status"] == "completed"
    image = client.get("/images?filename=x.png", headers=headers)
    assert image.content == b"PNG"
