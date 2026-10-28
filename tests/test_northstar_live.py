"""Tests for LIVE-SIM sockets, transfer, and channel shim."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import random
import socket
import tempfile
import threading
import time
import unittest

import northstar
import osps
from osps.framing import Frame, FrameError, FrameType, decode_frame, encode_frame
from northstar.live import (
    file_sha256,
    generate_payload,
    receive_packet,
    send_file,
    send_packet,
    serve_receiver,
)
from northstar.shim import bridge


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class NorthStarLiveTests(unittest.TestCase):
    """Real-socket LIVE-SIM behavior."""

    def test_north_star_frame_round_trip(self):
        frame = Frame(FrameType.DATA, 1, 4, b"payload")
        self.assertEqual(decode_frame(encode_frame(frame, b"key"), b"key"), frame)

    def test_packet_transport_uses_real_socket(self):
        left, right = socket.socketpair()
        try:
            send_packet(left, b"north-star")
            self.assertEqual(receive_packet(right), b"north-star")
        finally:
            left.close()
            right.close()

    def test_wrong_key_fails(self):
        wire = encode_frame(Frame(FrameType.DATA, 1, 0, b"x"), b"right")
        with self.assertRaises(FrameError):
            decode_frame(wire, b"wrong")

    def test_single_version_source(self):
        self.assertEqual(northstar.__version__, osps.__version__)

    def test_file_transfer_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "weights.bin"
            generate_payload(source, 300_000)
            port = _free_port()
            received = root / "received" / "weights.bin"
            with redirect_stdout(io.StringIO()):
                threading.Thread(
                    target=serve_receiver,
                    args=("127.0.0.1", port, root / "received", b"key"),
                    daemon=True,
                ).start()
                time.sleep(0.2)
                send_file(
                    source,
                    "127.0.0.1",
                    port,
                    b"key",
                    chunk_size=32 * 1024,
                    retry_delay=0.05,
                )
                for _ in range(50):
                    if received.exists():
                        break
                    time.sleep(0.05)
            self.assertEqual(file_sha256(received), file_sha256(source))

    def test_bridge_close_reaches_blocked_peer_promptly(self):
        sender, satellite_side = socket.socketpair()
        ground_side, receiver = socket.socketpair()
        sender.settimeout(5)
        try:
            self.enterContext(redirect_stdout(io.StringIO()))
            started = time.monotonic()
            worker = threading.Thread(
                target=bridge,
                args=(satellite_side, ground_side),
                kwargs={
                    "deadline": started + 0.2,
                    "bandwidth": 1_000_000,
                    "loss_rate": 0,
                    "jitter_ms": 0,
                    "randomizer": random.Random(1),
                },
                daemon=True,
            )
            worker.start()
            self.assertEqual(sender.recv(1), b"")
            self.assertLess(time.monotonic() - started, 2.0)
            worker.join(timeout=2)
        finally:
            sender.close()
            receiver.close()


if __name__ == "__main__":
    unittest.main()
