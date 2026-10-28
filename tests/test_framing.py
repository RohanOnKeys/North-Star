"""Tests for OSPS v2 framing and authenticated encryption."""

import struct
import unittest

from osps.framing import (
    FRAME_OVERHEAD,
    HEADER,
    MAGIC,
    Frame,
    FrameError,
    FrameType,
    decode_frame,
    encode_frame,
)


class FramingTests(unittest.TestCase):
    """Wire format, tamper detection, and versioning."""

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

    def test_header_tampering_is_rejected(self):
        wire = bytearray(encode_frame(Frame(FrameType.DATA, 1, 0, b"x"), b"key"))
        wire[HEADER.size - 5] ^= 1
        with self.assertRaises(FrameError):
            decode_frame(bytes(wire), b"key")

    def test_unencrypted_payload_is_still_authenticated(self):
        frame = Frame(FrameType.DATA, 1, 0, b"visible")
        wire = bytearray(encode_frame(frame, b"key", encrypt=False))
        self.assertIn(frame.payload, wire)
        self.assertEqual(decode_frame(bytes(wire), b"key"), frame)
        wire[HEADER.size + 12] ^= 1
        with self.assertRaises(FrameError):
            decode_frame(bytes(wire), b"key")

    def test_nonce_is_fresh_for_every_frame(self):
        frame = Frame(FrameType.DATA, 1, 0, b"same plaintext")
        self.assertNotEqual(encode_frame(frame, b"key"), encode_frame(frame, b"key"))

    def test_overhead_is_fixed(self):
        for size in (0, 1, 512, 32 * 1024):
            wire = encode_frame(Frame(FrameType.DATA, 1, 0, b"n" * size), b"key")
            self.assertEqual(len(wire), size + FRAME_OVERHEAD)

    def test_version_one_frames_are_rejected(self):
        legacy = HEADER.pack(MAGIC, 1, 2, 0, 0, 1, 0, 0) + bytes(28)
        with self.assertRaisesRegex(FrameError, "unsupported protocol version"):
            decode_frame(legacy, b"key")

    def test_header_layout_is_stable(self):
        wire = encode_frame(Frame(FrameType.DATA, 9, 3, b"abc"), b"key")
        magic, version, frame_type, _, _, stream, sequence, length = struct.unpack(
            "!4sBBBBIII", wire[: HEADER.size]
        )
        self.assertEqual(
            (magic, version, frame_type, stream, sequence, length),
            (b"NSTR", 2, 4, 9, 3, 3),
        )


if __name__ == "__main__":
    unittest.main()
