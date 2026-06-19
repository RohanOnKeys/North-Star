"""A real, deliberately tiny decoder for generated test tones only."""

from __future__ import annotations

from array import array
import math
from pathlib import Path
import wave

from .base import DecodeResult


class SyntheticToneDecoder:
    mode = "SYNTHETIC_TONE"

    def decode(self, path: Path) -> DecodeResult:
        with wave.open(str(path), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                return DecodeResult(
                    False, self.mode, "fixture must be mono 16-bit PCM", {}
                )
            rate = handle.getframerate()
            samples = array("h", handle.readframes(handle.getnframes()))
        if len(samples) < 2:
            return DecodeResult(False, self.mode, "fixture contains no signal", {})
        crossings = sum(
            1
            for previous, current in zip(samples, samples[1:])
            if previous <= 0 < current
        )
        duration = len(samples) / rate
        frequency = crossings / duration
        known = min((1000, 1500, 2000), key=lambda value: abs(value - frequency))
        success = abs(known - frequency) <= 40
        return DecodeResult(
            success,
            self.mode,
            "synthetic tone recognized" if success else "unknown synthetic tone",
            {
                "estimated_frequency_hz": round(frequency, 1),
                "nearest_fixture_frequency_hz": known,
                "duration_seconds": round(duration, 3),
            },
        )
