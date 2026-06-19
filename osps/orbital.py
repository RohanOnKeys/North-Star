"""Offline Skyfield pass prediction for North Star."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any

from skyfield.api import EarthSatellite, load, wgs84


@dataclass(frozen=True)
class PredictedPass:
    satellite: str
    start: datetime
    end: datetime
    max_elevation_degrees: float
    estimated_bandwidth: int

    @property
    def duration_seconds(self) -> int:
        return max(1, math.ceil((self.end - self.start).total_seconds()))

    def as_dict(self, simulation_start: datetime) -> dict[str, Any]:
        return {
            "name": f"{self.satellite}:{self.start.isoformat()}",
            "satellite": self.satellite,
            "start": max(
                0, math.floor((self.start - simulation_start).total_seconds())
            ),
            "duration": self.duration_seconds,
            "start_utc": self.start.isoformat().replace("+00:00", "Z"),
            "end_utc": self.end.isoformat().replace("+00:00", "Z"),
            "max_elevation_degrees": round(self.max_elevation_degrees, 2),
            "bandwidth": self.estimated_bandwidth,
        }


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_tle_set(path: Path, ts=None) -> list[EarthSatellite]:
    """Load name/line1/line2 triples without network access."""
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) % 3:
        raise ValueError("TLE file must contain name/line1/line2 triples")
    timescale = ts or load.timescale()
    return [
        EarthSatellite(lines[index + 1], lines[index + 2], lines[index], timescale)
        for index in range(0, len(lines), 3)
    ]


def estimate_bandwidth(
    elevation_degrees: float, minimum: int, maximum: int, threshold: float
) -> int:
    """Map threshold elevation to minimum bandwidth and zenith to maximum."""
    span = max(1.0, 90.0 - threshold)
    quality = min(1.0, max(0.0, (elevation_degrees - threshold) / span))
    return round(minimum + quality * (maximum - minimum))


def predict_passes(
    tle_path: Path,
    *,
    latitude_degrees: float,
    longitude_degrees: float,
    elevation_m: float,
    start: datetime,
    duration_seconds: int,
    elevation_threshold_degrees: float = 10.0,
    minimum_bandwidth: int = 64_000,
    maximum_bandwidth: int = 2_000_000,
) -> list[PredictedPass]:
    """Predict above-threshold passes using SGP4 and a fixed ground station."""
    ts = load.timescale()
    satellites = load_tle_set(tle_path, ts)
    observer = wgs84.latlon(
        latitude_degrees, longitude_degrees, elevation_m=elevation_m
    )
    end = start + timedelta(seconds=duration_seconds)
    t0 = ts.from_datetime(start)
    t1 = ts.from_datetime(end)
    passes: list[PredictedPass] = []

    for satellite in satellites:
        times, events = satellite.find_events(
            observer, t0, t1, altitude_degrees=elevation_threshold_degrees
        )
        rise = None
        culmination = None
        for time, event in zip(times, events):
            moment = time.utc_datetime().astimezone(timezone.utc)
            if event == 0:
                rise = moment
                culmination = None
            elif event == 1 and rise is not None:
                culmination = time
            elif event == 2 and rise is not None:
                bounded_start = max(start, rise)
                bounded_end = min(end, moment)
                if bounded_end > bounded_start:
                    peak_time = culmination if culmination is not None else time
                    elevation = (
                        (satellite - observer)
                        .at(peak_time)
                        .altaz()[0]
                        .degrees
                    )
                    passes.append(
                        PredictedPass(
                            satellite=satellite.name,
                            start=bounded_start,
                            end=bounded_end,
                            max_elevation_degrees=float(elevation),
                            estimated_bandwidth=estimate_bandwidth(
                                float(elevation),
                                minimum_bandwidth,
                                maximum_bandwidth,
                                elevation_threshold_degrees,
                            ),
                        )
                    )
                rise = None
                culmination = None

    return sorted(passes, key=lambda item: (item.start, item.satellite))


def predict_from_config(
    config: dict[str, Any], project_root: Path
) -> tuple[datetime, list[PredictedPass]]:
    orbital = config["orbital"]
    station = orbital["ground_station"]
    start = parse_utc(orbital["start_utc"])
    tle_path = Path(orbital["tle_file"])
    if not tle_path.is_absolute():
        tle_path = project_root / tle_path
    passes = predict_passes(
        tle_path,
        latitude_degrees=float(station["latitude_degrees"]),
        longitude_degrees=float(station["longitude_degrees"]),
        elevation_m=float(station.get("elevation_m", 0)),
        start=start,
        duration_seconds=int(orbital["duration_seconds"]),
        elevation_threshold_degrees=float(
            orbital.get("elevation_threshold_degrees", 10)
        ),
        minimum_bandwidth=int(orbital.get("minimum_bandwidth", 64_000)),
        maximum_bandwidth=int(orbital.get("maximum_bandwidth", 2_000_000)),
    )
    return start, passes
