import unittest

from osps.protocol import Endpoint, SessionState, WorkloadType


class PriorityTests(unittest.TestCase):
    def test_realtime_precedes_bulk(self):
        endpoint = Endpoint("ground", "satellite", b"key", chunk_size=32)
        bulk = endpoint.enqueue(WorkloadType.MODEL, b"m" * 64)
        realtime = endpoint.enqueue(WorkloadType.INFERENCE, b"request")
        endpoint.state = SessionState.ESTABLISHED
        frames = endpoint.next_frames(tick=0, byte_budget=4096)
        self.assertEqual(frames[0].stream_id, realtime)
        self.assertNotEqual(frames[0].stream_id, bulk)


if __name__ == "__main__":
    unittest.main()

