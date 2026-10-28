"""Pass-driven TCP channel shim for North Star LIVE-SIM."""

from __future__ import annotations

import json
import random
import socket
import threading
import time
from pathlib import Path

from osps.orbital import predict_from_config

from .live import log, receive_packet, send_packet


def hang_up(connection: socket.socket) -> None:
    """Close a socket so the peer sees FIN now.

    ``close()`` alone does not release a socket that another thread is blocked
    reading, so the peer would only notice when its own timeout expired.
    ``shutdown()`` wakes the blocked reader and sends FIN immediately.
    """
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    connection.close()


def pipe_packets(
    source: socket.socket,
    destination: socket.socket,
    *,
    deadline: float,
    bytes_per_second: float,
    loss_rate: float,
    jitter_ms: float,
    randomizer: random.Random,
    label: str,
) -> None:
    """Forward packets one way, applying loss, shaping, and the deadline."""
    while time.monotonic() < deadline:
        payload = receive_packet(source)
        if randomizer.random() < loss_rate:
            log("channel_packet_dropped", direction=label, bytes=len(payload))
            continue
        delay = len(payload) / max(1.0, bytes_per_second)
        delay += randomizer.uniform(0, jitter_ms / 1000)
        remaining = deadline - time.monotonic()
        if delay >= remaining:
            raise ConnectionError("contact ended during packet")
        time.sleep(delay)
        send_packet(destination, payload)


def bridge(
    satellite: socket.socket,
    ground: socket.socket,
    *,
    deadline: float,
    bandwidth: float,
    loss_rate: float,
    jitter_ms: float,
    randomizer: random.Random,
) -> None:
    """Relay both directions until the deadline or either side fails."""
    errors: list[Exception] = []

    def run(source, destination, label):
        """Pipe one direction and record the error that ended it."""
        try:
            pipe_packets(
                source,
                destination,
                deadline=deadline,
                bytes_per_second=bandwidth,
                loss_rate=loss_rate,
                jitter_ms=jitter_ms,
                randomizer=randomizer,
                label=label,
            )
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(
            target=run, args=(satellite, ground, "satellite_to_ground"), daemon=True
        ),
        threading.Thread(
            target=run, args=(ground, satellite, "ground_to_satellite"), daemon=True
        ),
    ]
    for thread in threads:
        thread.start()
    while time.monotonic() < deadline and all(thread.is_alive() for thread in threads):
        time.sleep(0.01)
    hang_up(satellite)
    hang_up(ground)
    for thread in threads:
        thread.join(timeout=0.2)
    if errors:
        log("channel_bridge_ended", reason=str(errors[0]))


def run_shim(
    scenario: Path,
    project_root: Path,
    *,
    listen_host: str = "127.0.0.1",
    listen_port: int = 9101,
    ground_host: str = "127.0.0.1",
    ground_port: int = 9100,
    time_scale: float = 1.0,
) -> int:
    """Serve the predicted pass schedule between sender and ground station."""
    config = json.loads(scenario.read_text(encoding="utf-8"))
    start, predicted = predict_from_config(config, project_root)
    if not predicted:
        raise SystemExit("No predicted contacts in scenario")
    scale = time_scale
    first_start = predicted[0].start
    schedule = [
        {
            "name": item.satellite,
            "open": (item.start - first_start).total_seconds() / scale,
            "close": (item.end - first_start).total_seconds() / scale,
            "bandwidth": item.estimated_bandwidth * scale,
            "elevation": item.max_elevation_degrees,
        }
        for item in predicted
    ]
    loss = float(config.get("live_channel", {}).get("loss_rate", 0.005))
    jitter = float(config.get("live_channel", {}).get("jitter_ms", 5))
    randomizer = random.Random(int(config.get("seed", 1)))
    origin = None
    last_refusal_log = 0.0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((listen_host, listen_port))
        server.listen()
        server.settimeout(0.1)
        log(
            "channel_ready",
            contacts=len(schedule),
            time_scale=scale,
            first_contact_delay_seconds=1,
            schedule_state="waiting_for_sender",
        )
        index = 0
        while index < len(schedule):
            if origin is None:
                try:
                    satellite, peer = server.accept()
                except socket.timeout:
                    continue
                origin = time.monotonic() + 1.0
                log("schedule_armed", peer=str(peer), first_contact_delay_seconds=1)
                hang_up(satellite)
                continue
            now = time.monotonic() - origin
            contact = schedule[index]
            if now >= contact["close"]:
                index += 1
                continue
            try:
                satellite, peer = server.accept()
            except socket.timeout:
                continue
            if now < contact["open"]:
                wall_now = time.monotonic()
                if wall_now - last_refusal_log >= 1.0:
                    log("connection_refused_no_line_of_sight", peer=str(peer))
                    last_refusal_log = wall_now
                hang_up(satellite)
                continue
            try:
                ground = socket.create_connection((ground_host, ground_port), timeout=2)
            except OSError as exc:
                log("ground_unavailable", reason=str(exc))
                hang_up(satellite)
                continue
            # The contact deadline, not a socket timeout, ends the bridge.
            ground.settimeout(None)
            deadline = origin + contact["close"]
            log(
                "contact_opened",
                satellite=contact["name"],
                max_elevation=round(contact["elevation"], 2),
                wall_duration_seconds=round(deadline - time.monotonic(), 3),
                shaped_bytes_per_second=round(contact["bandwidth"]),
            )
            bridge(
                satellite,
                ground,
                deadline=deadline,
                bandwidth=contact["bandwidth"],
                loss_rate=loss,
                jitter_ms=jitter,
                randomizer=randomizer,
            )
            log("contact_closed", satellite=contact["name"])
        log("schedule_exhausted")
    return 0
