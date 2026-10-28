# North Star

North Star is an experimental orbital data-streaming laboratory. It explores
resumable, authenticated AI workload transfer across intermittent satellite
contacts. The lab implements the **Orbital Streaming Protocol Secure (OSPS)**.

The simulator includes:

- an authenticated session handshake;
- versioned binary framing with ChaCha20-Poly1305 authenticated encryption;
- model, inference, result, telemetry, and control workload classes;
- QoS priority queues with starvation protection;
- chunked streams that fill each tick's byte budget up to the congestion
  window, with ACKs and retries;
- store-and-forward across interrupted orbital passes; and
- deterministic JSON-line or human-readable logs.

> Frames use an audited AEAD from the `cryptography` package, but the lab is
> still not a secure system: keys are static demo pre-shared keys, there is no
> key exchange or replay protection, and nothing has been reviewed for
> production use.

## Layout

| Path | Role |
|---|---|
| `osps/` | Protocol library: framing, endpoints, simulator, orbital prediction |
| `northstar/` | Application: command line and LIVE-SIM processes |
| `benchmarks/` | Framing benchmark |
| `radio_receiver/`, `laser_link/` | Separate hardware scaffolds |

## Quickstart

Requires Python 3.11+. The direct third-party dependencies are Skyfield and
cryptography. Every `python` command below is identical in bash and
PowerShell; only environment setup differs.

Create a virtual environment (optional):

```bash
# bash (Linux, macOS, Git Bash)
python -m venv .venv && source .venv/bin/activate
```

```powershell
# PowerShell
python -m venv .venv; .venv\Scripts\Activate.ps1
```

Install and run the interrupted-pass scenario:

```bash
python -m pip install -r requirements.txt
python -m northstar run scenarios/interrupted_pass.json --pretty
```

Or run the bundled scenario with defaults:

```bash
python -m northstar
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

Inspect the offline Skyfield schedule, then run North Star over those passes:

```bash
python -m northstar passes scenarios/real_orbits.json --pretty
python -m northstar run scenarios/real_orbits.json --pretty
```

Benchmark framing:

```bash
python -m benchmarks.framing_benchmark --iterations 2000
```

In the sample output, `pass-alpha` is deliberately interrupted before the model
stream completes. `pass-bravo` establishes a new link session, retries any
unacknowledged chunk, and finishes the retained stream.

See [REQUIREMENTS.md](REQUIREMENTS.md) for scope and success criteria and
[IMPLEMENTATION.md](IMPLEMENTATION.md) for architecture and design. The
RFC-style OSPS protocol description and DTN comparison are in
[SPEC.md](SPEC.md).

The bundled TLEs represent four LEO spacecraft and are intentionally static for
reproducibility. They are simulation inputs, not current tracking data.

## LIVE-SIM: three real processes

Open three terminals in the project folder and start them in this order:

```bash
# Terminal 1: ground receiver
python -m northstar ground --output-dir received

# Terminal 2: pass-driven channel
python -m northstar shim --time-scale 1200

# Terminal 3: satellite sender with a 2 MiB dummy model
python -m northstar satellite model_weights.bin --generate-bytes 2097152 --retry-delay 0.02
```

The sender reaches the receiver only through the pass-driven channel shim.
Outside predicted windows the connection is refused or dropped. During a
window, elevation-derived bandwidth, jitter, and packet loss are applied.
Progress survives later connections, and the final file is verified by
SHA-256. Logs use real UTC wall-clock timestamps.

The time scale defaults to `1`; the demonstration uses `1200` to compress the
fixed 24-hour schedule. It can also come from the `TIME_SCALE` environment
variable:

```bash
TIME_SCALE=1200 python -m northstar shim
```

```powershell
$env:TIME_SCALE = "1200"; python -m northstar shim
```

When the shim ends a contact it shuts both sockets down, so the sender notices
at once and reconnects for the next pass. `--ack-timeout` (default 5 s) only
bounds waits on a link that is still open; raise it for `--time-scale 1`, where
a 32 KiB chunk takes about 5.5 s on the slowest modeled pass.

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
