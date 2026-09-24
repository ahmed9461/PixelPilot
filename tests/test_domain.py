from pixelpilot.domain import GeneratedImage, GpuOffer, ReferenceImage


def test_reference_image_defaults_to_jpeg():
    item = ReferenceImage(data=b"image-bytes")
    assert item.data == b"image-bytes"
    assert item.mime_type == "image/jpeg"


def test_generated_image_metadata():
    result = GeneratedImage(
        data=b"png",
        mime_type="image/png",
        seed=123,
        width=1024,
        height=1024,
        model="Qwen/Qwen-Image-2.1",
        reference_count=2,
    )
    assert result.seed == 123
    assert result.reference_count == 2


def test_gpu_offer_public_dict_hides_raw_payload():
    offer = GpuOffer(
        offer_id=1,
        gpu_name="RTX 4090",
        gpu_ram_gb=24,
        price_per_hour=0.3,
        reliability=0.99,
        dlperf=30,
        raw={"secret": "raw"},
    )
    assert "raw" not in offer.public_dict()
