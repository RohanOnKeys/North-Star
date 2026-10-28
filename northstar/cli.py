"""North Star command line: simulator, pass schedule, and LIVE-SIM processes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from osps.orbital import predict_from_config
from osps.simulation import build_simulator, json_emitter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIO = PROJECT_ROOT / "scenarios" / "interrupted_pass.json"
DEFAULT_LIVE_SCENARIO = PROJECT_ROOT / "scenarios" / "live_real_orbits.json"


def pretty_emitter(record: dict[str, Any]) -> None:
    """Print a simulator event as one readable line."""
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
    """Load a JSON scenario file."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every subcommand."""
    parser = argparse.ArgumentParser(
        prog="north-star", description="North Star orbital streaming laboratory"
    )
    commands = parser.add_subparsers(dest="command")

    run = commands.add_parser("run", help="run a JSON scenario in the simulator")
    run.add_argument("scenario", nargs="?", type=Path, default=DEFAULT_SCENARIO)
    run.add_argument("--pretty", action="store_true", help="print readable logs")

    passes = commands.add_parser("passes", help="print a predicted orbital schedule")
    passes.add_argument("scenario", type=Path)
    passes.add_argument("--pretty", action="store_true", help="print a readable table")

    ground = commands.add_parser("ground", help="LIVE-SIM ground receiver")
    ground.add_argument("--host", default="127.0.0.1")
    ground.add_argument("--port", type=int, default=9100)
    ground.add_argument("--output-dir", type=Path, default=Path("received"))
    ground.add_argument("--key", default="north-star-live-key")

    shim = commands.add_parser("shim", help="LIVE-SIM pass-driven channel")
    shim.add_argument("--scenario", type=Path, default=DEFAULT_LIVE_SCENARIO)
    shim.add_argument("--listen-host", default="127.0.0.1")
    shim.add_argument("--listen-port", type=int, default=9101)
    shim.add_argument("--ground-host", default="127.0.0.1")
    shim.add_argument("--ground-port", type=int, default=9100)
    shim.add_argument(
        "--time-scale",
        type=float,
        default=None,
        help="simulation seconds per wall-clock second; defaults to TIME_SCALE or 1",
    )

    satellite = commands.add_parser("satellite", help="LIVE-SIM satellite sender")
    satellite.add_argument("file", type=Path)
    satellite.add_argument("--host", default="127.0.0.1")
    satellite.add_argument("--port", type=int, default=9101)
    satellite.add_argument("--key", default="north-star-live-key")
    satellite.add_argument("--chunk-size", type=int, default=32 * 1024)
    satellite.add_argument("--retry-delay", type=float, default=0.25)
    satellite.add_argument(
        "--ack-timeout",
        type=float,
        default=5.0,
        help="seconds to wait for a reply on an open link",
    )
    satellite.add_argument(
        "--generate-bytes",
        type=int,
        help="create a deterministic dummy model file before sending",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch a subcommand; with none, run the default scenario."""
    args = build_parser().parse_args(argv)
    if args.command == "ground":
        from .live import serve_receiver

        serve_receiver(args.host, args.port, args.output_dir, args.key.encode())
        return 0
    if args.command == "shim":
        from .shim import run_shim

        scale = args.time_scale
        if scale is None:
            scale = float(os.environ.get("TIME_SCALE", "1"))
        return run_shim(
            args.scenario,
            PROJECT_ROOT,
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            ground_host=args.ground_host,
            ground_port=args.ground_port,
            time_scale=scale,
        )
    if args.command == "satellite":
        from .live import generate_payload, send_file

        if args.generate_bytes:
            generate_payload(args.file, args.generate_bytes)
        send_file(
            args.file,
            args.host,
            args.port,
            args.key.encode(),
            chunk_size=args.chunk_size,
            retry_delay=args.retry_delay,
            ack_timeout=args.ack_timeout,
        )
        return 0

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
