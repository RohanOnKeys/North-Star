"""North Star laser-link software terminal.

This drives sockets and optical profiles only. It does not control a laser,
telescope, pointing system, or photodetector.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from northstar.live import generate_payload, send_file, serve_receiver
from northstar.orbital import predict_from_config

from .profile import derive_optical_windows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="North Star laser-link scaffold")
    commands = parser.add_subparsers(dest="command", required=True)
    receiver = commands.add_parser("receive")
    receiver.add_argument("--host", default="127.0.0.1")
    receiver.add_argument("--port", type=int, default=9200)
    receiver.add_argument("--output-dir", type=Path, default=Path("laser_received"))
    receiver.add_argument("--key", default="north-star-laser-key")
    sender = commands.add_parser("send")
    sender.add_argument("file", type=Path)
    sender.add_argument("--host", default="127.0.0.1")
    sender.add_argument("--port", type=int, default=9200)
    sender.add_argument("--key", default="north-star-laser-key")
    sender.add_argument("--generate-bytes", type=int)
    profile = commands.add_parser("profile")
    profile.add_argument(
        "--scenario", type=Path, default=Path("scenarios/real_orbits.json")
    )
    profile.add_argument("--bandwidth-bps", type=int, default=250_000_000)
    profile.add_argument("--wavelength-nm", type=int, default=1550)
    profile.add_argument("--acquisition-seconds", type=float, default=5)
    profile.add_argument(
        "--blocked-pass",
        type=int,
        action="append",
        default=[],
        help="zero-based pass index blocked by cloud/weather",
    )
    args = parser.parse_args(argv)
    if args.command == "receive":
        serve_receiver(args.host, args.port, args.output_dir, args.key.encode())
        return 0
    if args.command == "send":
        if args.generate_bytes:
            generate_payload(args.file, args.generate_bytes)
        send_file(args.file, args.host, args.port, args.key.encode())
        return 0
    config = json.loads(args.scenario.read_text(encoding="utf-8"))
    _, passes = predict_from_config(config, Path.cwd())
    windows = derive_optical_windows(
        passes,
        bandwidth_bps=args.bandwidth_bps,
        wavelength_nm=args.wavelength_nm,
        acquisition_seconds=args.acquisition_seconds,
        blocked_passes=set(args.blocked_pass),
    )
    for item in windows:
        print(
            json.dumps(
                {
                    "satellite": item.satellite,
                    "start_utc": item.start.isoformat().replace("+00:00", "Z"),
                    "end_utc": item.end.isoformat().replace("+00:00", "Z"),
                    "band_class": "Optical",
                    "wavelength_nm": item.wavelength_nm,
                    "bandwidth_bps": item.bandwidth_bps,
                    "cloud_sensitive": item.cloud_sensitive,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
