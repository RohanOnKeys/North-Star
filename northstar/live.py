"""Shared real-socket support for North Star LIVE-SIM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import time
from typing import Any

from .framing import Frame, FrameType, decode_frame, encode_frame

PACKET_LENGTH = struct.Struct("!I")
MAX_PACKET = 16 * 1024 * 1024


def log(event: str, **details: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        **details,
    }
    print(json.dumps(record, separators=(",", ":"), sort_keys=True), flush=True)


def receive_exact(connection: socket.socket, size: int) -> bytes:
    output = bytearray()
    while len(output) < size:
        block = connection.recv(size - len(output))
        if not block:
            raise ConnectionError("peer disconnected")
        output.extend(block)
    return bytes(output)


def send_packet(connection: socket.socket, payload: bytes) -> None:
    connection.sendall(PACKET_LENGTH.pack(len(payload)) + payload)


def receive_packet(connection: socket.socket) -> bytes:
    size = PACKET_LENGTH.unpack(receive_exact(connection, PACKET_LENGTH.size))[0]
    if size > MAX_PACKET:
        raise ValueError(f"packet exceeds {MAX_PACKET} bytes")
    return receive_exact(connection, size)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def generate_payload(path: Path, size: int) -> None:
    pattern = b"NORTH-STAR-MODEL-WEIGHTS-"
    remaining = size
    with path.open("wb") as handle:
        while remaining:
            block = pattern[:remaining]
            handle.write(block)
            remaining -= len(block)


@dataclass
class TransferMetadata:
    filename: str
    size: int
    chunk_size: int
    total_chunks: int
    sha256: str

    def encode(self) -> bytes:
        return json.dumps(self.__dict__, separators=(",", ":")).encode()

    @classmethod
    def decode(cls, payload: bytes) -> "TransferMetadata":
        return cls(**json.loads(payload.decode()))


def send_file(
    source: Path,
    host: str,
    port: int,
    key: bytes,
    *,
    chunk_size: int = 32 * 1024,
    retry_delay: float = 0.25,
) -> None:
    size = source.stat().st_size
    total = (size + chunk_size - 1) // chunk_size
    metadata = TransferMetadata(
        source.name, size, chunk_size, total, file_sha256(source)
    )
    next_sequence = 0
    log(
        "transfer_queued",
        file=str(source),
        bytes=size,
        chunks=total,
        sha256=metadata.sha256,
    )
    last_unavailable_log = 0.0
    while next_sequence < total:
        try:
            with socket.create_connection((host, port), timeout=2) as connection:
                connection.settimeout(5)
                send_packet(
                    connection,
                    encode_frame(Frame(FrameType.HELLO, 1, 0, metadata.encode()), key),
                )
                hello_ack = decode_frame(receive_packet(connection), key)
                if hello_ack.frame_type != FrameType.ACK:
                    raise ConnectionError("receiver rejected transfer")
                next_sequence = hello_ack.sequence
                log("link_established", resume_sequence=next_sequence)
                with source.open("rb") as handle:
                    handle.seek(next_sequence * chunk_size)
                    while next_sequence < total:
                        payload = handle.read(chunk_size)
                        frame = Frame(FrameType.DATA, 1, next_sequence, payload)
                        send_packet(connection, encode_frame(frame, key))
                        ack = decode_frame(receive_packet(connection), key)
                        if ack.frame_type != FrameType.ACK:
                            raise ConnectionError("unexpected receiver response")
                        next_sequence = ack.sequence
                        log(
                            "chunk_acked",
                            next_sequence=next_sequence,
                            total_chunks=total,
                            bytes_confirmed=min(size, next_sequence * chunk_size),
                        )
        except (ConnectionError, OSError, TimeoutError, ValueError) as exc:
            now = time.monotonic()
            if now - last_unavailable_log >= 1.0:
                log(
                    "link_unavailable",
                    reason=str(exc),
                    resume_sequence=next_sequence,
                )
                last_unavailable_log = now
            time.sleep(retry_delay)
    log("transfer_completed", file=str(source), sha256=metadata.sha256, bytes=size)


class FileReceiver:
    def __init__(self, output_dir: Path, key: bytes):
        self.output_dir = output_dir
        self.key = key
        output_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, metadata: TransferMetadata) -> tuple[Path, Path, Path]:
        safe_name = Path(metadata.filename).name
        final = self.output_dir / safe_name
        partial = self.output_dir / f"{safe_name}.part"
        state = self.output_dir / f"{safe_name}.state.json"
        return final, partial, state

    def _load_next(self, metadata: TransferMetadata, partial: Path, state: Path) -> int:
        if not partial.exists() or not state.exists():
            return 0
        saved = json.loads(state.read_text(encoding="utf-8"))
        if saved.get("sha256") != metadata.sha256:
            partial.unlink(missing_ok=True)
            state.unlink(missing_ok=True)
            return 0
        return int(saved.get("next_sequence", 0))

    def handle(self, connection: socket.socket, peer: tuple[str, int]) -> None:
        hello = decode_frame(receive_packet(connection), self.key)
        if hello.frame_type != FrameType.HELLO:
            raise ValueError("first frame must be HELLO")
        metadata = TransferMetadata.decode(hello.payload)
        final, partial, state = self._paths(metadata)
        if final.exists() and file_sha256(final) == metadata.sha256:
            send_packet(
                connection,
                encode_frame(
                    Frame(FrameType.ACK, 1, metadata.total_chunks), self.key
                ),
            )
            return
        next_sequence = self._load_next(metadata, partial, state)
        send_packet(
            connection,
            encode_frame(Frame(FrameType.ACK, 1, next_sequence), self.key),
        )
        log(
            "receiver_session",
            peer=f"{peer[0]}:{peer[1]}",
            file=metadata.filename,
            resume_sequence=next_sequence,
        )
        mode = "ab" if next_sequence else "wb"
        with partial.open(mode) as handle:
            while next_sequence < metadata.total_chunks:
                frame = decode_frame(receive_packet(connection), self.key)
                if frame.frame_type != FrameType.DATA:
                    raise ValueError("expected DATA")
                if frame.sequence == next_sequence:
                    handle.write(frame.payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    next_sequence += 1
                    state.write_text(
                        json.dumps(
                            {
                                "sha256": metadata.sha256,
                                "next_sequence": next_sequence,
                            }
                        ),
                        encoding="utf-8",
                    )
                send_packet(
                    connection,
                    encode_frame(
                        Frame(FrameType.ACK, 1, next_sequence), self.key
                    ),
                )
        actual = file_sha256(partial)
        if actual != metadata.sha256:
            raise ValueError(
                f"SHA-256 mismatch: expected {metadata.sha256}, received {actual}"
            )
        partial.replace(final)
        state.unlink(missing_ok=True)
        log(
            "file_reassembled",
            file=str(final),
            bytes=final.stat().st_size,
            sha256=actual,
            verified=True,
        )


def serve_receiver(host: str, port: int, output_dir: Path, key: bytes) -> None:
    receiver = FileReceiver(output_dir, key)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen()
        log("ground_station_listening", host=host, port=port)
        while True:
            connection, peer = server.accept()
            with connection:
                connection.settimeout(10)
                try:
                    receiver.handle(connection, peer)
                except (ConnectionError, OSError, ValueError) as exc:
                    log("receiver_link_lost", peer=f"{peer[0]}:{peer[1]}", reason=str(exc))
