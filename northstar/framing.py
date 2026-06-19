"""North Star authenticated wire framing."""

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
    pass


class FrameType(IntEnum):
    HELLO = 1
    DATA = 2
    ACK = 3
    ERROR = 4


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
        raise FrameError("frame too short")
    magic, version, type_value, flags, _, stream_id, sequence, length = HEADER.unpack(
        data[: HEADER.size]
    )
    if magic != MAGIC or version != VERSION:
        raise FrameError("invalid North Star frame header")
    if len(data) != HEADER.size + length + TAG_SIZE:
        raise FrameError("invalid payload length")
    expected = hmac.new(key, data[:-TAG_SIZE], hashlib.sha256).digest()[:TAG_SIZE]
    if not hmac.compare_digest(data[-TAG_SIZE:], expected):
        raise FrameError("frame authentication failed")
    payload = data[HEADER.size:-TAG_SIZE]
    if flags & 1:
        payload = _crypt(payload, key, stream_id, sequence)
    try:
        frame_type = FrameType(type_value)
    except ValueError as exc:
        raise FrameError("unknown frame type") from exc
    return Frame(frame_type, stream_id, sequence, payload, flags & ~1)
