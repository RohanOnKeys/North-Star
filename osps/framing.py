"""OSPS binary framing with ChaCha20-Poly1305 authenticated encryption.

This module is the single wire format shared by the simulator and LIVE-SIM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"NSTR"
VERSION = 2
NONCE_SIZE = 12
TAG_SIZE = 16
HEADER = struct.Struct("!4sBBBBIII")
FRAME_OVERHEAD = HEADER.size + NONCE_SIZE + TAG_SIZE
FLAG_ENCRYPTED = 1
_KEY_INFO = b"north-star/osps/v2/frame-key"


class FrameError(ValueError):
    """Raised when a frame is malformed or fails authentication."""


class FrameType(IntEnum):
    """Frame type codes carried in the header's type byte."""

    HELLO = 1
    CHALLENGE = 2
    AUTH = 3
    DATA = 4
    ACK = 5
    ERROR = 6


@dataclass(frozen=True)
class Frame:
    """One decoded OSPS frame."""

    frame_type: FrameType
    stream_id: int
    sequence: int
    payload: bytes = b""
    flags: int = 0


@lru_cache(maxsize=32)
def _cipher(key: bytes) -> ChaCha20Poly1305:
    """Derive a 256-bit AEAD key from a pre-shared key of any length."""
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_KEY_INFO
    ).derive(key)
    return ChaCha20Poly1305(derived)


def encode_frame(frame: Frame, key: bytes, *, encrypt: bool = True) -> bytes:
    """Serialize a frame as header, random nonce, payload, and AEAD tag.

    The header is always authenticated. The payload is encrypted when
    ``encrypt`` is true and it is non-empty, and authenticated otherwise.
    """
    flags = frame.flags | (FLAG_ENCRYPTED if encrypt and frame.payload else 0)
    header = HEADER.pack(
        MAGIC,
        VERSION,
        int(frame.frame_type),
        flags,
        0,
        frame.stream_id,
        frame.sequence,
        len(frame.payload),
    )
    nonce = os.urandom(NONCE_SIZE)
    if flags & FLAG_ENCRYPTED:
        sealed = _cipher(key).encrypt(nonce, frame.payload, header)
    else:
        sealed = frame.payload + _cipher(key).encrypt(
            nonce, b"", header + frame.payload
        )
    return header + nonce + sealed


def decode_frame(data: bytes, key: bytes) -> Frame:
    """Authenticate and parse a frame, raising ``FrameError`` on any defect."""
    if len(data) < FRAME_OVERHEAD:
        raise FrameError("frame is shorter than the minimum size")
    magic, version, type_value, flags, _, stream_id, sequence, length = HEADER.unpack(
        data[: HEADER.size]
    )
    if magic != MAGIC:
        raise FrameError("invalid frame magic")
    if version != VERSION:
        raise FrameError(f"unsupported protocol version: {version}")
    if len(data) != FRAME_OVERHEAD + length:
        raise FrameError("payload length does not match frame size")
    header = data[: HEADER.size]
    nonce = data[HEADER.size : HEADER.size + NONCE_SIZE]
    sealed = data[HEADER.size + NONCE_SIZE :]
    try:
        if flags & FLAG_ENCRYPTED:
            payload = _cipher(key).decrypt(nonce, sealed, header)
        else:
            payload = sealed[:-TAG_SIZE]
            _cipher(key).decrypt(nonce, sealed[-TAG_SIZE:], header + payload)
    except InvalidTag as exc:
        raise FrameError("frame authentication failed") from exc
    try:
        frame_type = FrameType(type_value)
    except ValueError as exc:
        raise FrameError(f"unknown frame type: {type_value}") from exc
    return Frame(frame_type, stream_id, sequence, payload, flags & ~FLAG_ENCRYPTED)
