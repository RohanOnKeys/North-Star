"""Decoder interface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DecodeResult:
    success: bool
    mode: str
    message: str
    details: dict


class Decoder(Protocol):
    mode: str

    def decode(self, path: Path) -> DecodeResult:
        ...
