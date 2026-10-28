"""Explicit non-decoder implementations for future radio modes."""

from pathlib import Path

from .base import DecodeResult


class StubDecoder:
    """Placeholder for a mode that is not implemented; never succeeds."""

    def __init__(self, mode: str):
        self.mode = mode

    def decode(self, path: Path) -> DecodeResult:
        """Report that this mode cannot be decoded yet."""
        return DecodeResult(
            False,
            self.mode,
            f"{self.mode} decoding is not yet implemented or validated",
            {"file": str(path), "status": "not_implemented"},
        )
