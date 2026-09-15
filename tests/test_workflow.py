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
        preset="raw",
        quality_profile="official",
    )
    wf = build_flux_krea_workflow(base, spec, filename_prefix="PixelPilot/g1")
    assert wf["4"]["inputs"]["text"] == spec.prompt
    assert wf["5"]["inputs"]["width"] == 896
    assert wf["5"]["inputs"]["height"] == 1120
    assert wf["5"]["inputs"]["batch_size"] == 2
    assert wf["7"]["inputs"]["seed"] == 123456
    assert wf["7"]["inputs"]["cfg"] == 1.0
    assert wf["7"]["inputs"]["sampler_name"] == "euler"
    assert wf["7"]["inputs"]["positive"] == ["4", 0]
    assert "10" not in wf
    assert wf["9"]["inputs"]["filename_prefix"] == "PixelPilot/g1"
    assert base["5"]["inputs"]["batch_size"] == 1


def test_krea_quality_adds_flux_guidance_without_rewriting_prompt():
    base = load_workflow(Path("resources/workflows/flux_krea_api.json"))
    prompt = "  Keep THIS prompt exactly, punctuation!  "
    spec = GenerationSpec(
        prompt=prompt,
        seed=42,
        steps=28,
        quality_profile="krea_quality",
    )

    wf = build_flux_krea_workflow(base, spec, filename_prefix="PixelPilot/quality")

    assert wf["4"]["inputs"]["text"] == prompt
    assert wf["7"]["inputs"]["steps"] == 28
    assert wf["7"]["inputs"]["cfg"] == 1.0
    assert wf["7"]["inputs"]["sampler_name"] == "euler"
    assert wf["7"]["inputs"]["scheduler"] == "simple"
    assert wf["10"]["class_type"] == "FluxGuidance"
    assert wf["10"]["inputs"]["conditioning"] == ["4", 0]
    assert wf["10"]["inputs"]["guidance"] == 4.5
    assert wf["7"]["inputs"]["positive"] == ["10", 0]
    assert "10" not in base


def test_workflow_rejects_unknown_quality_profile():
    base = load_workflow("resources/workflows/flux_krea_api.json")
    with pytest.raises(Exception):
        build_flux_krea_workflow(
            base,
            GenerationSpec(prompt="x", quality_profile="unknown"),
            filename_prefix="x",
        )


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
