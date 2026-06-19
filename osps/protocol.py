"""Core North Star queueing, chunking, session, ACK, and retry behavior."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import hashlib
import hmac
import json
from typing import Deque

from .framing import Frame, FrameType


class WorkloadType(str, Enum):
    CONTROL = "control"
    INFERENCE = "inference"
    RESULT = "result"
    TELEMETRY = "telemetry"
    MODEL = "model"


class Priority(IntEnum):
    CONTROL = 0
    REALTIME = 1
    TELEMETRY = 2
    BULK = 3


WORKLOAD_PRIORITY = {
    WorkloadType.CONTROL: Priority.CONTROL,
    WorkloadType.INFERENCE: Priority.REALTIME,
    WorkloadType.RESULT: Priority.REALTIME,
    WorkloadType.TELEMETRY: Priority.TELEMETRY,
    WorkloadType.MODEL: Priority.BULK,
}


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    HELLO_SENT = "hello_sent"
    CHALLENGE_RECEIVED = "challenge_received"
    AUTH_SENT = "auth_sent"
    ESTABLISHED = "established"


@dataclass
class Message:
    stream_id: int
    workload: WorkloadType
    payload: bytes
    source: str
    destination: str


@dataclass
class ChunkState:
    sequence: int
    payload: bytes
    sent_at: int | None = None
    attempts: int = 0
    acknowledged: bool = False


@dataclass
class OutboundStream:
    message: Message
    chunks: list[ChunkState]
    failed: bool = False

    @property
    def complete(self) -> bool:
        return all(chunk.acknowledged for chunk in self.chunks)


class PriorityQueue:
    """Priority FIFO with a burst cap to avoid bulk starvation."""

    def __init__(self, burst_limit: int = 4):
        self.queues: dict[Priority, Deque[int]] = {
            priority: deque() for priority in Priority
        }
        self.burst_limit = burst_limit
        self.high_burst = 0

    def push(self, stream_id: int, priority: Priority) -> None:
        self.queues[priority].append(stream_id)

    def pop(self) -> int | None:
        available = [p for p in Priority if self.queues[p]]
        if not available:
            return None
        if self.high_burst >= self.burst_limit:
            lower = [p for p in available if p > Priority.REALTIME]
            if lower:
                selected = min(lower)
                self.high_burst = 0
                return self.queues[selected].popleft()
        selected = min(available)
        if selected <= Priority.REALTIME:
            self.high_burst += 1
        else:
            self.high_burst = 0
        return self.queues[selected].popleft()

    def __len__(self) -> int:
        return sum(len(queue) for queue in self.queues.values())


@dataclass
class Endpoint:
    name: str
    peer: str
    psk: bytes
    chunk_size: int = 256
    retry_timeout: int = 2
    max_retries: int = 5
    state: SessionState = SessionState.DISCONNECTED
    congestion_window: int = 1
    streams: dict[int, OutboundStream] = field(default_factory=dict)
    incoming: dict[int, dict[int, bytes]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    completed_payloads: dict[int, bytes] = field(default_factory=dict)
    queue: PriorityQueue = field(default_factory=PriorityQueue)
    _next_stream_id: int = 1
    _nonce: bytes = b""

    def enqueue(self, workload: WorkloadType, payload: bytes) -> int:
        stream_id = self._next_stream_id
        self._next_stream_id += 1
        message = Message(stream_id, workload, payload, self.name, self.peer)
        raw_chunks = [
            payload[offset : offset + self.chunk_size]
            for offset in range(0, len(payload), self.chunk_size)
        ] or [b""]
        total = len(raw_chunks)
        chunks = []
        for sequence, raw in enumerate(raw_chunks):
            envelope = json.dumps(
                {
                    "workload": workload.value,
                    "total": total,
                    "data": raw.hex(),
                },
                separators=(",", ":"),
            ).encode()
            chunks.append(ChunkState(sequence, envelope))
        self.streams[stream_id] = OutboundStream(message, chunks)
        self.queue.push(stream_id, WORKLOAD_PRIORITY[workload])
        return stream_id

    def begin_handshake(self, tick: int) -> bytes:
        self.state = SessionState.HELLO_SENT
        self._nonce = hashlib.sha256(f"{self.name}:{self.peer}:{tick}".encode()).digest()[:16]
        return self._nonce

    def authenticate(self, nonce: bytes, claimed: bytes) -> bool:
        expected = hmac.new(
            self.psk, nonce + self.peer.encode() + self.name.encode(), hashlib.sha256
        ).digest()
        if hmac.compare_digest(expected, claimed):
            self.state = SessionState.ESTABLISHED
            return True
        self.state = SessionState.DISCONNECTED
        return False

    def make_auth(self, nonce: bytes) -> bytes:
        self.state = SessionState.AUTH_SENT
        return hmac.new(
            self.psk, nonce + self.name.encode() + self.peer.encode(), hashlib.sha256
        ).digest()

    def disconnect(self) -> None:
        self.state = SessionState.DISCONNECTED

    def next_frames(self, tick: int, byte_budget: int) -> list[Frame]:
        if self.state != SessionState.ESTABLISHED:
            return []
        frames: list[Frame] = []
        selected_streams: set[int] = set()
        allowance = max(1, self.congestion_window)
        inspections = len(self.queue)
        while inspections and len(frames) < allowance:
            inspections -= 1
            stream_id = self.queue.pop()
            if stream_id is None:
                break
            stream = self.streams[stream_id]
            if stream.complete or stream.failed:
                continue
            eligible = next(
                (
                    chunk
                    for chunk in stream.chunks
                    if not chunk.acknowledged
                    and (
                        chunk.sent_at is None
                        or tick - chunk.sent_at >= self.retry_timeout
                    )
                ),
                None,
            )
            self.queue.push(stream_id, WORKLOAD_PRIORITY[stream.message.workload])
            if eligible is None or stream_id in selected_streams:
                continue
            if eligible.attempts >= self.max_retries:
                stream.failed = True
                continue
            estimated_size = len(eligible.payload) + 36
            if estimated_size > byte_budget:
                continue
            eligible.sent_at = tick
            eligible.attempts += 1
            byte_budget -= estimated_size
            selected_streams.add(stream_id)
            frames.append(
                Frame(FrameType.DATA, stream_id, eligible.sequence, eligible.payload)
            )
        return frames

    def receive_data(self, frame: Frame) -> Frame:
        envelope = json.loads(frame.payload.decode())
        total = int(envelope["total"])
        self.incoming[frame.stream_id][frame.sequence] = bytes.fromhex(envelope["data"])
        if len(self.incoming[frame.stream_id]) == total:
            self.completed_payloads[frame.stream_id] = b"".join(
                self.incoming[frame.stream_id][index] for index in range(total)
            )
        return Frame(FrameType.ACK, frame.stream_id, frame.sequence)

    def receive_ack(self, frame: Frame) -> bool:
        stream = self.streams.get(frame.stream_id)
        if stream is None or frame.sequence >= len(stream.chunks):
            return False
        chunk = stream.chunks[frame.sequence]
        newly_acked = not chunk.acknowledged
        chunk.acknowledged = True
        if newly_acked:
            self.congestion_window = min(16, self.congestion_window + 1)
        return newly_acked

    def note_loss(self) -> None:
        self.congestion_window = max(1, self.congestion_window // 2)

    def pending_chunks(self) -> int:
        return sum(
            1
            for stream in self.streams.values()
            for chunk in stream.chunks
            if not chunk.acknowledged and not stream.failed
        )
