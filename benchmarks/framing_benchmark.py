"""Repeatable local North Star framing benchmark.

This measures Python framing cost only. It is not a network protocol shootout.
"""

from __future__ import annotations

import argparse
import json
import time

from northstar.framing import Frame, FrameType, decode_frame, encode_frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=32 * 1024)
    parser.add_argument("--iterations", type=int, default=2000)
    args = parser.parse_args()
    key = b"north-star-benchmark"
    payload = b"N" * args.chunk_size
    frame = Frame(FrameType.DATA, 1, 0, payload)

    start = time.perf_counter()
    encoded = None
    for sequence in range(args.iterations):
        encoded = encode_frame(
            Frame(frame.frame_type, frame.stream_id, sequence, payload), key
        )
    encode_seconds = time.perf_counter() - start

    wires = [
        encode_frame(Frame(FrameType.DATA, 1, sequence, payload), key)
        for sequence in range(args.iterations)
    ]
    start = time.perf_counter()
    for wire in wires:
        decode_frame(wire, key)
    decode_seconds = time.perf_counter() - start

    payload_bytes = args.chunk_size * args.iterations
    print(
        json.dumps(
            {
                "chunk_size": args.chunk_size,
                "iterations": args.iterations,
                "wire_frame_bytes": len(encoded),
                "encode_mib_per_second": round(
                    payload_bytes / encode_seconds / 1024 / 1024, 2
                ),
                "decode_mib_per_second": round(
                    payload_bytes / decode_seconds / 1024 / 1024, 2
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
