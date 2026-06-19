"""North Star live receiver process."""

from __future__ import annotations

import argparse
from pathlib import Path

from northstar.live import serve_receiver


def main() -> int:
    parser = argparse.ArgumentParser(description="North Star ground receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--output-dir", type=Path, default=Path("received"))
    parser.add_argument("--key", default="north-star-live-key")
    args = parser.parse_args()
    serve_receiver(args.host, args.port, args.output_dir, args.key.encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
