import unittest

from osps.framing import Frame, FrameError, FrameType, decode_frame, encode_frame


class FramingTests(unittest.TestCase):
    def test_encrypted_round_trip(self):
        frame = Frame(FrameType.DATA, 42, 7, b"orbital payload")
        wire = encode_frame(frame, b"key")
        self.assertNotIn(frame.payload, wire)
        self.assertEqual(decode_frame(wire, b"key"), frame)

    def test_tampering_is_rejected(self):
        wire = bytearray(encode_frame(Frame(FrameType.DATA, 1, 0, b"x"), b"key"))
        wire[-17] ^= 1
        with self.assertRaises(FrameError):
            decode_frame(bytes(wire), b"key")

    def test_wrong_key_is_rejected(self):
        wire = encode_frame(Frame(FrameType.ACK, 1, 0), b"right")
        with self.assertRaises(FrameError):
            decode_frame(wire, b"wrong")


if __name__ == "__main__":
    unittest.main()

