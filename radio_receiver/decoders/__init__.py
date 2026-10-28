"""Decoder registry for North Star radio input."""

from .base import DecodeResult
from .synthetic_tone import SyntheticToneDecoder
from .stubs import StubDecoder


def decoder_for(mode: str):
    """Return the decoder for a mode name; unknown modes get a stub."""
    normalized = mode.upper()
    if normalized == "SYNTHETIC_TONE":
        return SyntheticToneDecoder()
    return StubDecoder(normalized)


__all__ = ["DecodeResult", "decoder_for"]
