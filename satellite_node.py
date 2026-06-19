"""North Star live sender process."""

from __future__ import annotations

import argparse
from pathlib import Path

from northstar.live import generate_payload, send_file


def main() -> int:
    parser = argparse.ArgumentParser(description="North Star satellite sender")
    parser.add_argument("file", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9101)
    parser.add_argument("--key", default="north-star-live-key")
    parser.add_argument("--chunk-size", type=int, default=32 * 1024)
    parser.add_argument("--retry-delay", type=float, default=0.25)
    parser.add_argument(
        "--generate-bytes",
        type=int,
        help="create a deterministic dummy model file before sending",
    )
    args = parser.parse_args()
    if args.generate_bytes:
        generate_payload(args.file, args.generate_bytes)
    send_file(
        args.file,
        args.host,
        args.port,
        args.key.encode(),
        chunk_size=args.chunk_size,
        retry_delay=args.retry_delay,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
