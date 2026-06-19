import json
import unittest

from osps.protocol import Endpoint, SessionState, WorkloadType
from osps.simulation import build_simulator


class RetryTests(unittest.TestCase):
    def test_unacknowledged_chunk_is_retried(self):
        endpoint = Endpoint(
            "ground", "satellite", b"key", chunk_size=32, retry_timeout=2
        )
        stream_id = endpoint.enqueue(WorkloadType.MODEL, b"payload")
        endpoint.state = SessionState.ESTABLISHED
        first = endpoint.next_frames(0, 4096)
        self.assertEqual(len(first), 1)
        self.assertEqual(endpoint.next_frames(1, 4096), [])
        retry = endpoint.next_frames(2, 4096)
        self.assertEqual(retry[0].stream_id, stream_id)
        self.assertEqual(endpoint.streams[stream_id].chunks[0].attempts, 2)

    def test_scenario_resumes_after_interruption(self):
        config = {
            "protocol": {"chunk_size": 32, "retry_timeout": 1},
            "traffic": [{"source": "ground", "type": "model", "size": 180}],
            "contacts": [
                {
                    "name": "first",
                    "start": 0,
                    "duration": 3,
                    "interrupt_after": 1,
                    "bandwidth": 300,
                },
                {
                    "name": "second",
                    "start": 3,
                    "duration": 8,
                    "bandwidth": 1000,
                },
            ],
        }
        simulator = build_simulator(config)
        events = simulator.run()
        names = [event["event"] for event in events]
        self.assertIn("contact_interrupted", names)
        self.assertIn("stream_completed", names)
        self.assertEqual(simulator.ground.pending_chunks(), 0)

    def test_handshake_allows_bidirectional_transfer(self):
        config = {
            "traffic": [
                {"source": "ground", "type": "inference", "size": 20},
                {"source": "satellite", "type": "telemetry", "size": 20},
            ],
            "contacts": [
                {
                    "name": "duplex",
                    "start": 0,
                    "duration": 4,
                    "bandwidth": 1000,
                }
            ],
        }
        simulator = build_simulator(config)
        simulator.run()
        self.assertEqual(simulator.ground.pending_chunks(), 0)
        self.assertEqual(simulator.satellite.pending_chunks(), 0)
        completed_sources = {
            event["source"]
            for event in simulator.events
            if event["event"] == "stream_completed"
        }
        self.assertEqual(completed_sources, {"ground", "satellite"})


if __name__ == "__main__":
    unittest.main()
