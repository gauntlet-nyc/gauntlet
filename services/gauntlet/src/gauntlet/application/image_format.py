"""Recognize complete PNG/JPEG containers without decoding untrusted pixels.

This checks framing, required image sections, PNG CRCs and terminal markers.
It does not establish pixel correctness or any oracle outcome; callers must
still verify immutable evidence bindings and trusted browser measurements.
"""

import zlib
from typing import Literal

ImageMediaType = Literal["image/png", "image/jpeg"]
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_FRAMES = frozenset({0xC0, 0xC1, 0xC2})


def _png_complete(data: bytes) -> bool:
    offset = len(_PNG_SIGNATURE)
    image_data = False
    first = True
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset : offset + 4], "big")
        end = offset + 12 + size
        if end > len(data):
            return False
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : end - 4]
        if zlib.crc32(data[offset + 4 : end - 4]) != int.from_bytes(data[end - 4 : end], "big"):
            return False
        if first:
            if kind != b"IHDR" or size != 13:
                return False
            if not int.from_bytes(payload[:4], "big") or not int.from_bytes(payload[4:8], "big"):
                return False
        elif kind == b"IHDR":
            return False
        if kind == b"IDAT" and payload:
            image_data = True
        if kind == b"IEND":
            return size == 0 and image_data and end == len(data)
        first = False
        offset = end
    return False


def _jpeg_complete(data: bytes) -> bool:
    offset = 2  # SOI
    frame = False
    scan = False
    in_scan = False
    while offset < len(data):
        if in_scan:
            # Entropy bytes may contain stuffed FF00 or restart markers.
            marker_start = data.find(b"\xff", offset)
            if marker_start < 0:
                return False
            offset = marker_start
        if data[offset] != 0xFF:
            return False
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset == len(data):
            return False
        marker = data[offset]
        offset += 1
        if in_scan and (marker == 0 or 0xD0 <= marker <= 0xD7):
            continue
        in_scan = False
        if marker == 0xD9:
            return frame and scan and offset == len(data)
        if marker in {0, 0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
            return False
        if offset + 2 > len(data):
            return False
        size = int.from_bytes(data[offset : offset + 2], "big")
        end = offset + size
        if size < 2 or end > len(data):
            return False
        if marker in _JPEG_FRAMES:
            if size < 8 or not int.from_bytes(data[offset + 3 : offset + 5], "big"):
                return False
            if not int.from_bytes(data[offset + 5 : offset + 7], "big"):
                return False
            frame = True
        if marker == 0xDA:
            if not frame or size < 6 or end >= len(data) or data[end : end + 2] == b"\xff\xd9":
                return False
            scan = True
            in_scan = True
        offset = end
    return False


def screenshot_media_type(content: bytes) -> ImageMediaType | None:
    """Return actual supported media type, rejecting incomplete/malformed framing."""
    if content.startswith(_PNG_SIGNATURE) and _png_complete(content):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff") and _jpeg_complete(content):
        return "image/jpeg"
    return None


def valid_screenshot(content: bytes, media_type: str) -> bool:
    """An asserted MIME type must agree with the actual supported container."""
    return (
        media_type in {"image/png", "image/jpeg"} and screenshot_media_type(content) == media_type
    )
