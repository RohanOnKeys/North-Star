"""North Star binary framing and educational authenticated encryption."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import hmac
import struct

MAGIC = b"NSTR"
VERSION = 1
TAG_SIZE = 16
HEADER = struct.Struct("!4sBBBBIII")


class FrameError(ValueError):
    """Raised when a frame is malformed or fails authentication."""


class FrameType(IntEnum):
    HELLO = 1
    CHALLENGE = 2
    AUTH = 3
    DATA = 4
    ACK = 5
    ERROR = 6


@dataclass(frozen=True)
class Frame:
    frame_type: FrameType
    stream_id: int
    sequence: int
    payload: bytes = b""
    flags: int = 0


def _keystream(key: bytes, stream_id: int, sequence: int, length: int) -> bytes:
    seed = struct.pack("!II", stream_id, sequence)
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(
            hmac.new(key, seed + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        )
        counter += 1
    return bytes(output[:length])


def _crypt(data: bytes, key: bytes, stream_id: int, sequence: int) -> bytes:
    return bytes(
        value ^ mask
        for value, mask in zip(data, _keystream(key, stream_id, sequence, len(data)))
    )


def encode_frame(frame: Frame, key: bytes, *, encrypt: bool = True) -> bytes:
    flags = frame.flags | (1 if encrypt and frame.payload else 0)
    payload = (
        _crypt(frame.payload, key, frame.stream_id, frame.sequence)
        if flags & 1
        else frame.payload
    )
    header = HEADER.pack(
        MAGIC,
        VERSION,
        int(frame.frame_type),
        flags,
        0,
        frame.stream_id,
        frame.sequence,
        len(payload),
    )
    tag = hmac.new(key, header + payload, hashlib.sha256).digest()[:TAG_SIZE]
    return header + payload + tag


def decode_frame(data: bytes, key: bytes) -> Frame:
    if len(data) < HEADER.size + TAG_SIZE:
        raise FrameError("frame is shorter than the minimum size")
    magic, version, type_value, flags, _, stream_id, sequence, length = HEADER.unpack(
        data[: HEADER.size]
    )
    if magic != MAGIC:
        raise FrameError("invalid frame magic")
    if version != VERSION:
        raise FrameError(f"unsupported protocol version: {version}")
    expected_size = HEADER.size + length + TAG_SIZE
    if len(data) != expected_size:
        raise FrameError("payload length does not match frame size")
    signed = data[:-TAG_SIZE]
    supplied_tag = data[-TAG_SIZE:]
    expected_tag = hmac.new(key, signed, hashlib.sha256).digest()[:TAG_SIZE]
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise FrameError("frame authentication failed")
    payload = data[HEADER.size:-TAG_SIZE]
    if flags & 1:
        payload = _crypt(payload, key, stream_id, sequence)
    try:
        frame_type = FrameType(type_value)
    except ValueError as exc:
        raise FrameError(f"unknown frame type: {type_value}") from exc
    return Frame(frame_type, stream_id, sequence, payload, flags & ~1)
