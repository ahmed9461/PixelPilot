from pathlib import Path

import pytest

from pixelpilot.domain import GenerationSpec
from pixelpilot.workflow import build_flux2_workflow, extract_history_images, load_workflow


def test_build_flux2_workflow_patches_runtime_fields_without_rewriting_prompt():
    base = load_workflow(Path("resources/workflows/flux2_dev_api.json"))
    prompt = "  Keep THIS prompt exactly, punctuation!  "
    spec = GenerationSpec(
        prompt=prompt,
        width=896,
        height=1120,
        seed=123456,
        steps=28,
        batch_size=2,
        preset="raw",
        quality_profile="flux2_balanced",
    )
    wf = build_flux2_workflow(base, spec, filename_prefix="PixelPilot/g1")

    assert wf["4"]["inputs"]["text"] == prompt
    assert wf["5"]["inputs"]["guidance"] == 4.0
    assert wf["6"]["inputs"]["width"] == 896
    assert wf["6"]["inputs"]["height"] == 1120
    assert wf["6"]["inputs"]["batch_size"] == 2
    assert wf["7"]["inputs"]["noise_seed"] == 123456
    assert wf["8"]["inputs"]["sampler_name"] == "euler"
    assert wf["9"]["inputs"]["steps"] == 28
    assert wf["9"]["inputs"]["width"] == 896
    assert wf["9"]["inputs"]["height"] == 1120
    assert wf["13"]["inputs"]["filename_prefix"] == "PixelPilot/g1"
    assert base["6"]["inputs"]["batch_size"] == 1
    assert base["4"]["inputs"]["text"] == "A realistic photograph"


def test_flux2_quality_supports_50_steps_without_touching_prompt():
    base = load_workflow(Path("resources/workflows/flux2_dev_api.json"))
    prompt = "Hands, skin, fabric -- exact text."
    spec = GenerationSpec(
        prompt=prompt,
        seed=42,
        steps=50,
        quality_profile="flux2_quality",
    )

    wf = build_flux2_workflow(base, spec, filename_prefix="PixelPilot/quality")

    assert wf["4"]["inputs"]["text"] == prompt
    assert wf["5"]["inputs"]["guidance"] == 4.0
    assert wf["9"]["inputs"]["steps"] == 50
    assert wf["7"]["inputs"]["noise_seed"] == 42
    assert wf["13"]["inputs"]["filename_prefix"] == "PixelPilot/quality"


def test_legacy_generation_profile_can_be_rerun_on_flux2():
    base = load_workflow("resources/workflows/flux2_dev_api.json")
    wf = build_flux2_workflow(
        base,
        GenerationSpec(prompt="legacy", quality_profile="krea_quality", steps=28),
        filename_prefix="legacy",
    )
    assert wf["4"]["inputs"]["text"] == "legacy"


def test_workflow_rejects_unknown_quality_profile():
    base = load_workflow("resources/workflows/flux2_dev_api.json")
    with pytest.raises(Exception):
        build_flux2_workflow(
            base,
            GenerationSpec(prompt="x", quality_profile="unknown"),
            filename_prefix="x",
        )


def test_workflow_rejects_non_aligned_size():
    base = load_workflow("resources/workflows/flux2_dev_api.json")
    with pytest.raises(Exception):
        build_flux2_workflow(
            base,
            GenerationSpec(prompt="x", width=1001, height=1024),
            filename_prefix="x",
        )


def test_extract_history_images():
    item = {
        "outputs": {
            "13": {
                "images": [
                    {"filename": "a.png", "subfolder": "PixelPilot", "type": "output"},
                    {"filename": "b.png", "type": "output"},
                ]
            }
        }
    }
    images = extract_history_images(item)
    assert [x["filename"] for x in images] == ["a.png", "b.png"]
