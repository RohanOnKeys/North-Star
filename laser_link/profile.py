"""Optical-window derivation kept separate from radio/audio code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True)
class OpticalWindow:
    satellite: str
    start: datetime
    end: datetime
    bandwidth_bps: int
    wavelength_nm: int
    cloud_sensitive: bool


def derive_optical_windows(
    orbital_passes: Iterable,
    *,
    bandwidth_bps: int,
    wavelength_nm: int = 1550,
    acquisition_seconds: float = 5,
    cloud_sensitive: bool = True,
    blocked_passes: set[int] | None = None,
) -> list[OpticalWindow]:
    """Apply acquisition time and explicit weather blocks to orbital passes."""
    blocked = blocked_passes or set()
    output = []
    for index, orbital_pass in enumerate(orbital_passes):
        if index in blocked:
            continue
        start = orbital_pass.start + timedelta(seconds=acquisition_seconds)
        if start >= orbital_pass.end:
            continue
        output.append(
            OpticalWindow(
                orbital_pass.satellite,
                start,
                orbital_pass.end,
                bandwidth_bps,
                wavelength_nm,
                cloud_sensitive,
            )
        )
    return output
