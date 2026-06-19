"""North Star audio-jack receiver command line."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio_io import list_devices, record_wav
from .decoders import decoder_for
from .generate_fixtures import generate
from .input_sources import build_input_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="North Star radio receiver scaffold")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-devices")
    record = commands.add_parser("record")
    record.add_argument("output", type=Path)
    record.add_argument("--seconds", type=float, default=10)
    record.add_argument("--device", type=int)
    decode = commands.add_parser("decode")
    decode.add_argument("input", type=Path)
    decode.add_argument("--mode", required=True)
    receive = commands.add_parser(
        "receive", help="decode from hardware or an existing WAV file"
    )
    receive.add_argument("--source", choices=("hardware", "wav"), required=True)
    receive.add_argument("--input", type=Path)
    receive.add_argument("--mode", required=True)
    receive.add_argument("--seconds", type=float, default=10)
    receive.add_argument("--device", type=int)
    receive.add_argument("--sample-rate", type=int, default=48_000)
    receive.add_argument("--recording-output", type=Path)
    fixtures = commands.add_parser("generate-fixtures")
    fixtures.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "fixtures",
    )
    args = parser.parse_args(argv)
    if args.command == "list-devices":
        print(json.dumps(list_devices(), indent=2))
        return 0
    if args.command == "record":
        record_wav(args.output, args.seconds, device=args.device)
        print(json.dumps({"recorded": str(args.output), "seconds": args.seconds}))
        return 0
    if args.command == "generate-fixtures":
        for path in generate(args.output_dir):
            print(path)
        return 0
    if args.command == "receive":
        try:
            source = build_input_source(
                args.source,
                input_path=args.input,
                seconds=args.seconds,
                device=args.device,
                sample_rate=args.sample_rate,
                output=args.recording_output,
            )
            acquired = source.acquire()
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(
                json.dumps(
                    {
                        "success": False,
                        "source": args.source,
                        "message": str(exc),
                    },
                    indent=2,
                )
            )
            return 2
        result = decoder_for(args.mode).decode(acquired)
        print(
            json.dumps(
                {
                    **result.__dict__,
                    "source": source.name,
                    "captured_file": str(acquired),
                },
                indent=2,
            )
        )
        return 0 if result.success else 2
    result = decoder_for(args.mode).decode(args.input)
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
