import json
from pathlib import Path


def test_model_manifest_has_expected_flux2_files():
    data = json.loads(Path("resources/model_manifest.json").read_text(encoding="utf-8"))
    files = {
        item.get("target_name") or Path(item["filename"]).name: item
        for item in data["files"]
    }
    assert set(files) == {
        "flux2_dev_fp8mixed.safetensors",
        "mistral_3_small_flux2_fp8.safetensors",
        "flux2-vae.safetensors",
    }
    assert all(item["repo_id"] == "Comfy-Org/flux2-dev" for item in files.values())
    assert all(item["requires_hf_token"] is False for item in files.values())
    assert files["mistral_3_small_flux2_fp8.safetensors"]["target_subdir"] == "text_encoders"
