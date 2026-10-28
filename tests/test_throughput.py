"""Tests for multi-chunk scheduling and the binary envelope."""

from pathlib import Path
import unittest

from northstar.cli import load_config
from osps.framing import FRAME_OVERHEAD, encode_frame
from osps.protocol import CHUNK_HEADER, Endpoint, SessionState, WorkloadType
from osps.simulation import build_simulator

ROOT = Path(__file__).resolve().parent.parent


class ThroughputTests(unittest.TestCase):
    """Link utilization and wire efficiency."""

    def test_one_stream_sends_several_chunks_per_tick(self):
        endpoint = Endpoint("ground", "satellite", b"key", chunk_size=64)
        stream_id = endpoint.enqueue(WorkloadType.MODEL, b"m" * 640)
        endpoint.state = SessionState.ESTABLISHED
        endpoint.congestion_window = 4
        frames = endpoint.next_frames(tick=0, byte_budget=1_000_000)
        self.assertEqual([frame.sequence for frame in frames], [0, 1, 2, 3])
        self.assertTrue(all(frame.stream_id == stream_id for frame in frames))

    def test_byte_budget_limits_chunks_per_tick(self):
        endpoint = Endpoint("ground", "satellite", b"key", chunk_size=64)
        endpoint.enqueue(WorkloadType.MODEL, b"m" * 640)
        endpoint.state = SessionState.ESTABLISHED
        endpoint.congestion_window = 16
        frame_size = 64 + CHUNK_HEADER.size + FRAME_OVERHEAD
        frames = endpoint.next_frames(tick=0, byte_budget=frame_size * 3 + 1)
        self.assertEqual(len(frames), 3)

    def test_blocked_high_priority_stream_does_not_starve_bulk(self):
        endpoint = Endpoint(
            "ground", "satellite", b"key", chunk_size=64, retry_timeout=5
        )
        endpoint.enqueue(WorkloadType.INFERENCE, b"i" * 10)
        bulk = endpoint.enqueue(WorkloadType.MODEL, b"m" * 640)
        endpoint.state = SessionState.ESTABLISHED
        endpoint.congestion_window = 4
        endpoint.next_frames(tick=0, byte_budget=1_000_000)
        frames = endpoint.next_frames(tick=1, byte_budget=1_000_000)
        self.assertTrue(frames)
        self.assertTrue(all(frame.stream_id == bulk for frame in frames))

    def test_data_envelope_is_raw_bytes(self):
        endpoint = Endpoint("ground", "satellite", b"key", chunk_size=512)
        endpoint.enqueue(WorkloadType.MODEL, b"m" * 1024)
        endpoint.state = SessionState.ESTABLISHED
        frame = endpoint.next_frames(tick=0, byte_budget=1_000_000)[0]
        self.assertEqual(len(frame.payload), 512 + CHUNK_HEADER.size)
        wire = encode_frame(frame, b"key")
        self.assertGreater(512 / len(wire), 0.9)

    def test_receiver_reassembles_binary_chunks(self):
        sender = Endpoint("ground", "satellite", b"key", chunk_size=3)
        receiver = Endpoint("satellite", "ground", b"key")
        payload = bytes(range(10))
        stream_id = sender.enqueue(WorkloadType.TELEMETRY, payload)
        sender.state = SessionState.ESTABLISHED
        sender.congestion_window = 16
        for frame in sender.next_frames(tick=0, byte_budget=1_000_000):
            sender.receive_ack(receiver.receive_data(frame))
        self.assertEqual(receiver.completed_payloads[stream_id], payload)
        self.assertEqual(sender.pending_chunks(), 0)

    def test_real_orbit_model_finishes_in_first_pass(self):
        config = load_config(ROOT / "scenarios" / "real_orbits.json")
        simulator = build_simulator(config, project_root=ROOT)
        events = simulator.run()
        first_pass = simulator.contacts[0].name
        completed = {
            event["workload"]: event["contact"]
            for event in events
            if event["event"] == "stream_completed"
        }
        self.assertEqual(
            completed,
            {"model": first_pass, "inference": first_pass, "telemetry": first_pass},
        )


if __name__ == "__main__":
    unittest.main()
