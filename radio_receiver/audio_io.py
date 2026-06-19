"""Audio device and WAV helpers for the North Star radio scaffold."""

from __future__ import annotations

from pathlib import Path
import wave


def _sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        raise RuntimeError(
            "Live audio requires the optional dependency: "
            "python -m pip install -r requirements-radio.txt"
        ) from exc
    return sounddevice


def list_devices() -> list[dict]:
    sounddevice = _sounddevice()
    output = []
    for index, device in enumerate(sounddevice.query_devices()):
        output.append(
            {
                "index": index,
                "name": device["name"],
                "input_channels": device["max_input_channels"],
                "default_samplerate": device["default_samplerate"],
            }
        )
    return output


def record_wav(
    destination: Path,
    seconds: float,
    *,
    sample_rate: int = 48_000,
    device: int | None = None,
) -> None:
    sounddevice = _sounddevice()
    frames = sounddevice.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device,
    )
    sounddevice.wait()
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames.tobytes())
