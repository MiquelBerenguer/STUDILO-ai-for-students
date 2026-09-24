"""File type detection by magic bytes (never by extension)."""

from __future__ import annotations

from typing import Literal

FileType = Literal["pdf", "png", "jpeg", "heic", "webp", "tiff", "text", "unsupported"]
IMAGE_TYPES: frozenset[str] = frozenset({"png", "jpeg", "heic", "webp", "tiff"})

_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif"}


def detect_type(data: bytes) -> FileType:
    head = data[:32]
    if head.startswith(b"%PDF-") or data[:1024].find(b"%PDF-") != -1:
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(head) >= 12 and head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return "heic"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if _looks_like_text(data):
        return "text"
    return "unsupported"


def _looks_like_text(data: bytes) -> bool:
    sample = data[:65536]
    if not sample or b"\x00" in sample or sample.startswith(b"PK\x03\x04"):
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte char cut at the sample boundary is fine; anything else is binary.
        if exc.start < len(sample) - 4:
            return False
        text = sample[:exc.start].decode("utf-8")
    controls = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t\f")
    return controls <= len(text) * 0.001
