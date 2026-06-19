"""Generate deterministic synthetic WAV fixtures; these are not recordings."""

from __future__ import annotations

from array import array
import math
from pathlib import Path
import wave


def generate(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    rate = 8_000
    duration = 0.5
    for frequency in (1000, 1500, 2000):
        samples = array(
            "h",
            (
                int(12_000 * math.sin(2 * math.pi * frequency * index / rate))
                for index in range(int(rate * duration))
            ),
        )
        path = directory / f"synthetic_{frequency}hz.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(samples.tobytes())
        paths.append(path)
    return paths
