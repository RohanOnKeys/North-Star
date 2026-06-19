"""North Star simulation command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from osps.cli import load_config, pretty_emitter
from osps.simulation import build_simulator, json_emitter

from .orbital import predict_from_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "interrupted_pass.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="north-star", description="North Star orbital streaming laboratory"
    )
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run")
    run.add_argument("scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO)
    run.add_argument("--pretty", action="store_true")
    passes = commands.add_parser("passes")
    passes.add_argument("scenario", type=Path)
    passes.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    scenario = getattr(args, "scenario", DEFAULT_SCENARIO)
    config = load_config(scenario)
    if args.command == "passes":
        start, predicted = predict_from_config(config, PROJECT_ROOT)
        for item in predicted:
            record = item.as_dict(start)
            if args.pretty:
                print(
                    f"{record['satellite']:<20} {record['start_utc']} -> "
                    f"{record['end_utc']} max={record['max_elevation_degrees']:>5.1f}° "
                    f"bandwidth={record['bandwidth']} B/s"
                )
            else:
                print(json.dumps(record, separators=(",", ":"), sort_keys=True))
        return 0
    simulator = build_simulator(
        config,
        emit=pretty_emitter if getattr(args, "pretty", False) else json_emitter,
        project_root=PROJECT_ROOT,
    )
    simulator.run()
    return 1 if simulator.ground.pending_chunks() + simulator.satellite.pending_chunks() else 0
