"""Explicit non-decoder implementations for future radio modes."""

from pathlib import Path

from .base import DecodeResult


class StubDecoder:
    def __init__(self, mode: str):
        self.mode = mode

    def decode(self, path: Path) -> DecodeResult:
        return DecodeResult(
            False,
            self.mode,
            f"{self.mode} decoding is not yet implemented or validated",
            {"file": str(path), "status": "not_implemented"},
        )
