"""Decoder interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DecodeResult:
    """Outcome of decoding one capture."""

    success: bool
    mode: str
    message: str
    details: dict


class Decoder(Protocol):
    """Interface every radio mode decoder implements."""

    mode: str

    def decode(self, path: Path) -> DecodeResult:
        """Decode the WAV capture at ``path``."""
        ...
