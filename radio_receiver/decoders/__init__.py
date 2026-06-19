"""Decoder registry for North Star radio input."""

from .base import DecodeResult
from .synthetic_tone import SyntheticToneDecoder
from .stubs import StubDecoder


def decoder_for(mode: str):
    normalized = mode.upper()
    if normalized == "SYNTHETIC_TONE":
        return SyntheticToneDecoder()
    return StubDecoder(normalized)


__all__ = ["DecodeResult", "decoder_for"]
