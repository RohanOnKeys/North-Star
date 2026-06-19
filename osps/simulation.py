"""Deterministic contact-window simulation for North Star."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any, Callable

from .framing import FrameType, decode_frame, encode_frame
from .protocol import Endpoint, SessionState, WorkloadType


@dataclass(frozen=True)
class Contact:
    name: str
    start: int
    duration: int
    bandwidth: int
    latency: int = 0
    loss_rate: float = 0.0
    drop_sequences: tuple[int, ...] = ()
    interrupt_after: int | None = None

    def active(self, simulation_second: int) -> bool:
        elapsed = simulation_second - self.start
        if elapsed < 0 or elapsed >= self.duration:
            return False
        return self.interrupt_after is None or elapsed < self.interrupt_after


class Simulator:
    def __init__(
        self,
        ground: Endpoint,
        satellite: Endpoint,
        contacts: list[Contact],
        *,
        seed: int = 1,
        tick_seconds: int = 1,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.ground = ground
        self.satellite = satellite
        self.contacts = contacts
        self.random = random.Random(seed)
        self.tick_seconds = tick_seconds
        self.events: list[dict[str, Any]] = []
        self.emit = emit
        self._active_contact: Contact | None = None
        self._forced_drops_used: set[tuple[str, int, int]] = set()

    def log(self, tick: int, event: str, **details: Any) -> None:
        record = {
            "time": tick * self.tick_seconds,
            "event": event,
            **details,
            "ground_queue": self.ground.pending_chunks(),
            "satellite_queue": self.satellite.pending_chunks(),
        }
        self.events.append(record)
        if self.emit:
            self.emit(record)

    def _handshake(self, tick: int, contact: Contact) -> None:
        nonce = self.ground.begin_handshake(tick)
        self.log(tick, "handshake_hello", contact=contact.name, node=self.ground.name)
        self.satellite.state = SessionState.CHALLENGE_RECEIVED
        proof = self.ground.make_auth(nonce)
        if not self.satellite.authenticate(nonce, proof):
            self.log(tick, "authentication_failed", contact=contact.name)
            return
        reverse_nonce = self.satellite.begin_handshake(tick)
        reverse_proof = self.satellite.make_auth(reverse_nonce)
        if self.ground.authenticate(reverse_nonce, reverse_proof):
            self.satellite.state = SessionState.ESTABLISHED
            self.log(tick, "session_established", contact=contact.name)
        else:
            self.satellite.disconnect()
            self.log(tick, "authentication_failed", contact=contact.name)

    def _should_drop(self, contact: Contact, stream_id: int, sequence: int) -> bool:
        key = (contact.name, stream_id, sequence)
        if sequence in contact.drop_sequences and key not in self._forced_drops_used:
            self._forced_drops_used.add(key)
            return True
        return self.random.random() < contact.loss_rate

    def _transfer(
        self,
        tick: int,
        contact: Contact,
        sender: Endpoint,
        receiver: Endpoint,
        budget: int,
    ) -> int:
        transferred = 0
        for frame in sender.next_frames(tick, budget):
            encoded = encode_frame(frame, sender.psk)
            if len(encoded) > budget:
                break
            if self._should_drop(contact, frame.stream_id, frame.sequence):
                sender.note_loss()
                self.log(
                    tick,
                    "frame_dropped",
                    contact=contact.name,
                    source=sender.name,
                    stream=frame.stream_id,
                    sequence=frame.sequence,
                    bytes=len(encoded),
                )
                budget -= len(encoded)
                continue
            decoded = decode_frame(encoded, receiver.psk)
            ack = receiver.receive_data(decoded)
            ack_wire = encode_frame(ack, receiver.psk)
            sender.receive_ack(decode_frame(ack_wire, sender.psk))
            transferred += len(encoded)
            budget -= len(encoded)
            stream = sender.streams[frame.stream_id]
            self.log(
                tick,
                "chunk_acked",
                contact=contact.name,
                source=sender.name,
                stream=frame.stream_id,
                workload=stream.message.workload.value,
                sequence=frame.sequence,
                attempt=stream.chunks[frame.sequence].attempts,
                bytes=len(encoded),
                latency_ms=contact.latency,
                congestion_window=sender.congestion_window,
            )
            if stream.complete:
                self.log(
                    tick,
                    "stream_completed",
                    contact=contact.name,
                    source=sender.name,
                    stream=frame.stream_id,
                    workload=stream.message.workload.value,
                    payload_bytes=len(stream.message.payload),
                )
        return transferred

    def run(self, until: int | None = None) -> list[dict[str, Any]]:
        if not self.contacts:
            return self.events
        end_second = until if until is not None else max(
            contact.start + contact.duration for contact in self.contacts
        )
        end_tick = math.ceil(end_second / self.tick_seconds)
        previous: Contact | None = None
        for tick in range(end_tick + 1):
            simulation_second = tick * self.tick_seconds
            active = next(
                (c for c in self.contacts if c.active(simulation_second)), None
            )
            if active is not previous:
                if previous is not None:
                    interrupted = (
                        previous.interrupt_after is not None
                        and simulation_second
                        >= previous.start + previous.interrupt_after
                        and simulation_second
                        < previous.start + previous.duration
                    )
                    self.ground.disconnect()
                    self.satellite.disconnect()
                    self.log(
                        tick,
                        "contact_interrupted" if interrupted else "contact_closed",
                        contact=previous.name,
                    )
                if active is not None:
                    self.log(tick, "contact_opened", contact=active.name)
                    self._handshake(tick, active)
                previous = active
            if active and self.ground.state == SessionState.ESTABLISHED:
                budget = active.bandwidth * self.tick_seconds
                used = self._transfer(
                    tick, active, self.ground, self.satellite, budget // 2
                )
                used += self._transfer(
                    tick, active, self.satellite, self.ground, budget - budget // 2
                )
                self.log(
                    tick,
                    "link_tick",
                    contact=active.name,
                    bytes_transferred=used,
                    byte_budget=budget,
                )
        if previous is not None:
            self.ground.disconnect()
            self.satellite.disconnect()
            self.log(end_tick + 1, "contact_closed", contact=previous.name)
        return self.events


def build_simulator(
    config: dict[str, Any],
    emit: Callable[[dict[str, Any]], None] | None = None,
    *,
    project_root: Path | None = None,
) -> Simulator:
    protocol = config.get("protocol", {})
    psk = config.get("pre_shared_key", "north-star-demo-key").encode()
    common = {
        "psk": psk,
        "chunk_size": int(protocol.get("chunk_size", 256)),
        "retry_timeout": int(protocol.get("retry_timeout", 2)),
        "max_retries": int(protocol.get("max_retries", 5)),
    }
    ground = Endpoint("ground", "satellite", **common)
    satellite = Endpoint("satellite", "ground", **common)
    for item in config.get("traffic", []):
        endpoint = ground if item.get("source", "ground") == "ground" else satellite
        size = int(item.get("size", 0))
        pattern = item.get("pattern", item["type"]).encode()
        payload = (pattern * ((size // len(pattern)) + 1))[:size]
        endpoint.enqueue(WorkloadType(item["type"]), payload)
    contact_items = config.get("contacts", [])
    if "orbital" in config:
        from .orbital import predict_from_config

        root = project_root or Path(__file__).resolve().parent.parent
        simulation_start, passes = predict_from_config(config, root)
        contact_items = [
            {
                **predicted.as_dict(simulation_start),
                "latency_ms": config["orbital"].get("latency_ms", 20),
                "loss_rate": config["orbital"].get("loss_rate", 0),
            }
            for predicted in passes
        ]
    contacts = [
        Contact(
            name=item["name"],
            start=int(item["start"]),
            duration=int(item["duration"]),
            bandwidth=int(item["bandwidth"]),
            latency=int(item.get("latency_ms", 0)),
            loss_rate=float(item.get("loss_rate", 0)),
            drop_sequences=tuple(item.get("drop_sequences", [])),
            interrupt_after=item.get("interrupt_after"),
        )
        for item in contact_items
    ]
    return Simulator(
        ground,
        satellite,
        contacts,
        seed=int(config.get("seed", 1)),
        tick_seconds=int(config.get("tick_seconds", 1)),
        emit=emit,
    )


def json_emitter(record: dict[str, Any]) -> None:
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))
