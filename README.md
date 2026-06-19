# North Star

North Star is an experimental orbital data-streaming laboratory. It explores
resumable, authenticated AI workload transfer across intermittent satellite
contacts. The project and protocol are both called **North Star**.

The simulator includes:

- an authenticated session handshake;
- versioned binary framing and authenticated payload encryption;
- model, inference, result, telemetry, and control workload classes;
- QoS priority queues with starvation protection;
- chunked streams, ACKs, retries, and congestion-window behavior;
- store-and-forward across interrupted orbital passes; and
- deterministic JSON-line or human-readable logs.

> The included cipher is educational and must not be used for real security.

## Quickstart

Requires Python 3.11+. Skyfield is the only direct third-party dependency.

```powershell
python -m pip install -r requirements.txt
python -m northstar run scenarios/interrupted_pass.json --pretty
```

Or run the bundled scenario with defaults:

```powershell
python -m northstar
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

Inspect the offline Skyfield schedule, then run North Star over those passes:

```powershell
python -m northstar passes scenarios/real_orbits.json --pretty
python -m northstar run scenarios/real_orbits.json --pretty
```

In the sample output, `pass-alpha` is deliberately interrupted before the model
stream completes. `pass-bravo` establishes a new link session, retries any
unacknowledged chunk, and finishes the retained stream.

See [REQUIREMENTS.md](REQUIREMENTS.md) for scope and success criteria and
[IMPLEMENTATION.md](IMPLEMENTATION.md) for architecture and design. The
RFC-style implemented protocol description and DTN comparison are in
[SPEC.md](SPEC.md).

The bundled TLEs represent four LEO spacecraft and are intentionally static for
reproducibility. They are simulation inputs, not current tracking data.

## LIVE-SIM: three real processes

Open three terminals:

```powershell
# Terminal 1
python ground_station.py --output-dir received

# Terminal 2
python channel_shim.py --time-scale 1200

# Terminal 3
python satellite_node.py model_weights.bin --generate-bytes 2097152 --retry-delay 0.02
```

The sender reaches the receiver only through the pass-driven channel shim.
Outside predicted windows the connection is refused or dropped. During a
window, elevation-derived bandwidth, jitter, and packet loss are applied.
Progress survives later connections, and the final file is verified by
SHA-256. Logs use real UTC wall-clock timestamps.

`TIME_SCALE` defaults to `1`; the demonstration uses `1200` to compress the
fixed 24-hour schedule.

The orbital clock arms when the first sender connection reaches the shim, so
opening terminals slowly does not consume the predicted passes.

## Separate hardware paths

- [Radio/audio-jack receiver](radio_receiver/README.md)
- [Laser-link software scaffold](laser_link/README.md)

The radio and laser programs are deliberately separate. Neither claims real
hardware support yet.

## Reports and explanations

- [Curious dudes guide](curious_dudes.md)
- [Results, speed, and protocol comparison](RESULTS_SPEED_COMPARISON.md)
- [Formal protocol specification](SPEC.md)
