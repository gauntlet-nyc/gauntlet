"""Evidence image framing is shared and fails closed independently of MIME claims."""

import pytest
from image_samples import JPEG, PNG

from gauntlet.application.image_format import screenshot_media_type, valid_screenshot


@pytest.mark.parametrize("content,media", [(PNG, "image/png"), (JPEG, "image/jpeg")])
def test_complete_browser_images_have_matching_media(content: bytes, media: str) -> None:
    assert screenshot_media_type(content) == media
    assert valid_screenshot(content, media)
    assert not valid_screenshot(content, "image/jpeg" if media == "image/png" else "image/png")
    assert not valid_screenshot(content, "application/octet-stream")


@pytest.mark.parametrize("content", [PNG, JPEG])
def test_every_truncated_prefix_is_rejected(content: bytes) -> None:
    for length in range(len(content)):
        assert screenshot_media_type(content[:length]) is None, length


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"GIF89a",
        b"<html>not a screenshot</html>",
        b"\x89PNG\r\n\x1a\nnot-image-data",
        b"\xff\xd8\xff\xd9",
        b"\xff\xd8\xff\xe0\x00\x01\xff\xd9",
        PNG + b"trailing",
        JPEG + b"trailing",
        PNG[:-1] + bytes([PNG[-1] ^ 1]),
        JPEG[:4] + b"\xff\xff" + JPEG[6:],
    ],
)
def test_invalid_or_unsupported_container_rejected(content: bytes) -> None:
    assert screenshot_media_type(content) is None
    assert not valid_screenshot(content, "image/png")
    assert not valid_screenshot(content, "image/jpeg")
