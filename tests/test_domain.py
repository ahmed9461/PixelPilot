import base64

from pixelpilot.domain import MediaInput, UserInput


def test_text_message_is_passed_without_rewrite():
    message = UserInput(text="اشرح لي هذه الفكرة").to_openai_message()
    assert message == {"role": "user", "content": "اشرح لي هذه الفكرة"}


def test_image_message_contains_exact_caption_and_image_data():
    raw = b"image-bytes"
    message = UserInput(
        text="وش موجود بالصورة؟",
        media=(MediaInput(kind="image", data=raw, mime_type="image/jpeg"),),
    ).to_openai_message()
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "image_url"
    assert message["content"][0]["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    assert message["content"][1] == {"type": "text", "text": "وش موجود بالصورة؟"}


def test_bare_audio_does_not_invent_text_instruction():
    message = UserInput(media=(MediaInput(kind="audio", data=b"voice", mime_type="audio/ogg"),)).to_openai_message()
    assert message == {"role": "user", "content": [{"type": "audio_url", "audio_url": {"url": "data:audio/ogg;base64,dm9pY2U="}}]}


def test_video_uses_openai_video_url_part_without_invented_caption():
    raw = b"video-bytes"
    message = UserInput(
        media=(MediaInput(kind="video", data=raw, mime_type="video/mp4"),),
    ).to_openai_message()
    assert message == {
        "role": "user",
        "content": [
            {
                "type": "video_url",
                "video_url": {
                    "url": "data:video/mp4;base64," + base64.b64encode(raw).decode("ascii")
                },
            }
        ],
    }
