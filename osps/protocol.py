"""Core North Star queueing, chunking, session, ACK, and retry behavior."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import hashlib
import hmac
import struct
from typing import Deque

from .framing import FRAME_OVERHEAD, Frame, FrameType


class WorkloadType(str, Enum):
    """Application workload classes carried by a stream."""

    CONTROL = "control"
    INFERENCE = "inference"
    RESULT = "result"
    TELEMETRY = "telemetry"
    MODEL = "model"


class Priority(IntEnum):
    """Scheduling priority; lower values are sent first."""

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

WORKLOAD_CODES = {
    WorkloadType.CONTROL: 0,
    WorkloadType.INFERENCE: 1,
    WorkloadType.RESULT: 2,
    WorkloadType.TELEMETRY: 3,
    WorkloadType.MODEL: 4,
}

# Prefix on every DATA payload: workload code and total chunk count.
CHUNK_HEADER = struct.Struct("!BI")


class SessionState(str, Enum):
    """Link session states for one endpoint."""

    DISCONNECTED = "disconnected"
    HELLO_SENT = "hello_sent"
    CHALLENGE_RECEIVED = "challenge_received"
    AUTH_SENT = "auth_sent"
    ESTABLISHED = "established"


@dataclass
class Message:
    """An application message queued for transfer."""

    stream_id: int
    workload: WorkloadType
    payload: bytes
    source: str
    destination: str


@dataclass
class ChunkState:
    """Send and acknowledgement state for one outbound chunk."""

    sequence: int
    payload: bytes
    sent_at: int | None = None
    attempts: int = 0
    acknowledged: bool = False


@dataclass
class OutboundStream:
    """A queued message split into chunks."""

    message: Message
    chunks: list[ChunkState]
    failed: bool = False

    @property
    def complete(self) -> bool:
        """Whether every chunk has been acknowledged."""
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
        """Append a stream to the queue for its priority."""
        self.queues[priority].append(stream_id)

    def pop(self) -> int | None:
        """Remove and return the next stream, or ``None`` when empty."""
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
    """One side of an OSPS link: outbound streams plus reassembly state."""

    name: str
    peer: str
    psk: bytes
    chunk_size: int = 256
    retry_timeout: int = 2
    max_retries: int = 5
    max_congestion_window: int = 16
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
        """Split a payload into chunks, queue it, and return its stream ID."""
        stream_id = self._next_stream_id
        self._next_stream_id += 1
        message = Message(stream_id, workload, payload, self.name, self.peer)
        raw_chunks = [
            payload[offset : offset + self.chunk_size]
            for offset in range(0, len(payload), self.chunk_size)
        ] or [b""]
        prefix = CHUNK_HEADER.pack(WORKLOAD_CODES[workload], len(raw_chunks))
        chunks = [
            ChunkState(sequence, prefix + raw)
            for sequence, raw in enumerate(raw_chunks)
        ]
        self.streams[stream_id] = OutboundStream(message, chunks)
        self.queue.push(stream_id, WORKLOAD_PRIORITY[workload])
        return stream_id

    def begin_handshake(self, tick: int) -> bytes:
        """Start a handshake and return the challenge nonce."""
        self.state = SessionState.HELLO_SENT
        self._nonce = hashlib.sha256(f"{self.name}:{self.peer}:{tick}".encode()).digest()[:16]
        return self._nonce

    def authenticate(self, nonce: bytes, claimed: bytes) -> bool:
        """Check the peer's proof; establish the session if it matches."""
        expected = hmac.new(
            self.psk, nonce + self.peer.encode() + self.name.encode(), hashlib.sha256
        ).digest()
        if hmac.compare_digest(expected, claimed):
            self.state = SessionState.ESTABLISHED
            return True
        self.state = SessionState.DISCONNECTED
        return False

    def make_auth(self, nonce: bytes) -> bytes:
        """Return this endpoint's HMAC proof for a challenge nonce."""
        self.state = SessionState.AUTH_SENT
        return hmac.new(
            self.psk, nonce + self.name.encode() + self.peer.encode(), hashlib.sha256
        ).digest()

    def disconnect(self) -> None:
        """Drop the session; queued and acknowledged state is kept."""
        self.state = SessionState.DISCONNECTED

    def next_frames(self, tick: int, byte_budget: int) -> list[Frame]:
        """Select DATA frames for this tick in priority order.

        A stream may contribute several chunks per tick. Selection stops when
        the congestion window is full or no eligible chunk fits the budget.
        """
        if self.state != SessionState.ESTABLISHED:
            return []
        frames: list[Frame] = []
        parked: list[int] = []
        allowance = max(1, self.congestion_window)
        while len(frames) < allowance:
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
            if eligible is None:
                parked.append(stream_id)
                continue
            if eligible.attempts >= self.max_retries:
                stream.failed = True
                continue
            frame_size = len(eligible.payload) + FRAME_OVERHEAD
            if frame_size > byte_budget:
                parked.append(stream_id)
                continue
            eligible.sent_at = tick
            eligible.attempts += 1
            byte_budget -= frame_size
            frames.append(
                Frame(FrameType.DATA, stream_id, eligible.sequence, eligible.payload)
            )
            self.queue.push(stream_id, WORKLOAD_PRIORITY[stream.message.workload])
        for stream_id in parked:
            self.queue.push(
                stream_id, WORKLOAD_PRIORITY[self.streams[stream_id].message.workload]
            )
        return frames

    def receive_data(self, frame: Frame) -> Frame:
        """Store a DATA chunk, reassemble when complete, and return its ACK."""
        if len(frame.payload) < CHUNK_HEADER.size:
            raise ValueError("DATA payload is shorter than the chunk header")
        _, total = CHUNK_HEADER.unpack_from(frame.payload)
        self.incoming[frame.stream_id][frame.sequence] = frame.payload[
            CHUNK_HEADER.size :
        ]
        if len(self.incoming[frame.stream_id]) == total:
            self.completed_payloads[frame.stream_id] = b"".join(
                self.incoming[frame.stream_id][index] for index in range(total)
            )
        return Frame(FrameType.ACK, frame.stream_id, frame.sequence)

    def receive_ack(self, frame: Frame) -> bool:
        """Mark a chunk acknowledged; return whether it was newly acked."""
        stream = self.streams.get(frame.stream_id)
        if stream is None or frame.sequence >= len(stream.chunks):
            return False
        chunk = stream.chunks[frame.sequence]
        newly_acked = not chunk.acknowledged
        chunk.acknowledged = True
        if newly_acked:
            self.congestion_window = min(
                self.max_congestion_window, self.congestion_window + 1
            )
        return newly_acked

    def note_loss(self) -> None:
        """Halve the congestion window after a lost frame."""
        self.congestion_window = max(1, self.congestion_window // 2)

    def pending_chunks(self) -> int:
        """Count unacknowledged chunks on streams that have not failed."""
        return sum(
            1
            for stream in self.streams.values()
            for chunk in stream.chunks
            if not chunk.acknowledged and not stream.failed
        )
