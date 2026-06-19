import socket
import unittest

from northstar.framing import Frame, FrameError, FrameType, decode_frame, encode_frame
from northstar.live import receive_packet, send_packet


class NorthStarLiveTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
