"""Selectable hardware and no-hardware inputs for the radio receiver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Protocol

from .audio_io import record_wav


class InputSource(Protocol):
    name: str

    def acquire(self) -> Path:
        ...


@dataclass
class WavInputSource:
    path: Path
    name: str = "wav"

    def acquire(self) -> Path:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        return self.path


@dataclass
class SoundDeviceInputSource:
    seconds: float
    device: int | None = None
    sample_rate: int = 48_000
    output: Path | None = None
    name: str = "hardware"

    def acquire(self) -> Path:
        destination = self.output
        if destination is None:
            temporary = tempfile.NamedTemporaryFile(
                prefix="north_star_radio_", suffix=".wav", delete=False
            )
            temporary.close()
            destination = Path(temporary.name)
        record_wav(
            destination,
            self.seconds,
            sample_rate=self.sample_rate,
            device=self.device,
        )
        return destination


def build_input_source(
    source: str,
    *,
    input_path: Path | None = None,
    seconds: float = 10,
    device: int | None = None,
    sample_rate: int = 48_000,
    output: Path | None = None,
) -> InputSource:
    if source == "wav":
        if input_path is None:
            raise ValueError("--input is required when --source wav")
        return WavInputSource(input_path)
    if source == "hardware":
        return SoundDeviceInputSource(
            seconds=seconds,
            device=device,
            sample_rate=sample_rate,
            output=output,
        )
    raise ValueError(f"unknown input source: {source}")
