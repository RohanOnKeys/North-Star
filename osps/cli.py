"""Command-line interface for the North Star simulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .orbital import predict_from_config
from .simulation import build_simulator, json_emitter

DEFAULT_SCENARIO = (
    Path(__file__).resolve().parent.parent / "scenarios" / "interrupted_pass.json"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def pretty_emitter(record: dict[str, Any]) -> None:
    core = (
        f"T+{record['time']:03d}s  {record['event']:<20} "
        f"GQ={record['ground_queue']:<3} SQ={record['satellite_queue']:<3}"
    )
    details = " ".join(
        f"{key}={value}"
        for key, value in record.items()
        if key not in {"time", "event", "ground_queue", "satellite_queue"}
    )
    print(f"{core} {details}".rstrip())


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="north-star", description="Simulate the OSPS orbital streaming protocol"
    )
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="run a JSON scenario")
    run.add_argument("scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO)
    run.add_argument("--pretty", action="store_true", help="print readable logs")
    passes = subparsers.add_parser("passes", help="print a predicted orbital schedule")
    passes.add_argument("scenario", type=Path)
    passes.add_argument("--pretty", action="store_true", help="print a readable table")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario = getattr(args, "scenario", DEFAULT_SCENARIO)
    pretty = getattr(args, "pretty", False)
    config = load_config(scenario)
    if args.command == "passes":
        start, predicted = predict_from_config(config, PROJECT_ROOT)
        for orbital_pass in predicted:
            item = orbital_pass.as_dict(start)
            if pretty:
                print(
                    f"{item['satellite']:<20} {item['start_utc']} -> "
                    f"{item['end_utc']}  max={item['max_elevation_degrees']:>5.1f}° "
                    f"bandwidth={item['bandwidth']} B/s"
                )
            else:
                print(json.dumps(item, separators=(",", ":"), sort_keys=True))
        return 0
    simulator = build_simulator(
        config,
        emit=pretty_emitter if pretty else json_emitter,
        project_root=PROJECT_ROOT,
    )
    simulator.run()
    incomplete = simulator.ground.pending_chunks() + simulator.satellite.pending_chunks()
    return 1 if incomplete else 0
