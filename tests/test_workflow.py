from pathlib import Path

import pytest

from pixelpilot.domain import GenerationSpec
from pixelpilot.workflow import build_flux_krea_workflow, extract_history_images, load_workflow


def test_build_flux_krea_workflow_patches_runtime_fields():
    base = load_workflow(Path("resources/workflows/flux_krea_api.json"))
    spec = GenerationSpec(
        prompt="A realistic person outdoors",
        width=896,
        height=1120,
        seed=123456,
        steps=20,
        batch_size=2,
        preset="outdoor",
    )
    wf = build_flux_krea_workflow(base, spec, filename_prefix="PixelPilot/g1")
    assert wf["4"]["inputs"]["text"] == spec.prompt
    assert wf["5"]["inputs"]["width"] == 896
    assert wf["5"]["inputs"]["height"] == 1120
    assert wf["5"]["inputs"]["batch_size"] == 2
    assert wf["7"]["inputs"]["seed"] == 123456
    assert wf["7"]["inputs"]["cfg"] == 1.0
    assert wf["7"]["inputs"]["sampler_name"] == "euler"
    assert wf["9"]["inputs"]["filename_prefix"] == "PixelPilot/g1"
    assert base["5"]["inputs"]["batch_size"] == 1


def test_workflow_rejects_non_aligned_size():
    base = load_workflow("resources/workflows/flux_krea_api.json")
    with pytest.raises(Exception):
        build_flux_krea_workflow(
            base,
            GenerationSpec(prompt="x", width=1001, height=1024),
            filename_prefix="x",
        )


def test_extract_history_images():
    item = {
        "outputs": {
            "9": {
                "images": [
                    {"filename": "a.png", "subfolder": "PixelPilot", "type": "output"},
                    {"filename": "b.png", "type": "output"},
                ]
            }
        }
    }
    images = extract_history_images(item)
    assert [x["filename"] for x in images] == ["a.png", "b.png"]
