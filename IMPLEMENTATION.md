# North Star Implementation

## Architecture

```text
AI consumer
    |
    v
+----------------+        contact window         +----------------+
| Ground station | <============================> | Satellite node |
| OSPS endpoint  |   bandwidth / latency / loss   | OSPS endpoint  |
+-------+--------+                                +--------+-------+
        |                                                  |
  priority queues                                    receive store
  retry/ACK state                                    reassembly
        |                                                  |
        +------------ Simulation scheduler ----------------+
                 repeated passes and simulated time
```

The scheduler owns simulated time and link availability. Endpoints own protocol
state, queues, chunk state, and reassembly. Frames are encoded to bytes before
crossing the simulated link and decoded at the peer.

## Repository layout

```text
northstar/
  framing.py        OSPS live wire framing
  live.py           real socket transfer and disk-backed resumption
  orbital.py        public orbital prediction interface
  cli.py            simulation CLI
simulation internals are retained behind the public `northstar` package
  __init__.py       public package metadata
  __main__.py       compatibility simulation entry point
  cli.py            CLI parsing and scenario loading
  framing.py        frame codec, integrity, simulated encryption
  protocol.py       messages, QoS queue, endpoint and retry state
  orbital.py        offline TLE loading and Skyfield pass prediction
  simulation.py     contacts, scheduler and structured event log
data/
  north_star_leo.tle
scenarios/
  interrupted_pass.json
  real_orbits.json
tests/
  test_framing.py
  test_orbital.py
  test_priority.py
  test_retry.py
```

## Protocol state machine

```text
DISCONNECTED
    | contact opens
    v
HELLO_SENT -> CHALLENGE_RECEIVED -> AUTH_SENT -> ESTABLISHED
    ^                                                |
    | invalid auth / contact closes / fatal error    |
    +------------------------------------------------+
```

The handshake is compressed into a deterministic exchange by the simulation,
but it creates and validates the same control values that would be sent as
frames. Logical message and ACK state is not discarded when link state returns
to `DISCONNECTED`.

## Simulation model

A scenario defines nodes, tick duration, chunk size, retry limits, initial
traffic, and either explicit test contacts or an `orbital` prediction block. A
contact has:

- start and duration in simulated seconds;
- bandwidth in bytes per simulated second;
- one-way latency for log visibility;
- deterministic packet loss controls; and
- an optional forced interruption time.

At each tick, the scheduler opens/closes contacts, performs a handshake, assigns
a byte budget, and asks each endpoint for frames. Frames may be dropped by the
link. Delivered frames are authenticated, reassembled, and acknowledged.
Unacknowledged chunks age by ticks and become eligible for retransmission.

### Real pass predictor

The North Star lab's orbital predictor uses Skyfield's SGP4 implementation and a
bundled static TLE set.
For every satellite it finds rise, culmination, and set events above the
configured minimum elevation. Each result is converted into the existing
`Contact(name, start, duration, bandwidth, latency, ...)` interface; the
protocol and endpoint modules do not know whether a contact was handwritten or
predicted.

Bandwidth is a scenario estimate, not an RF link budget. It scales linearly
from `minimum_bandwidth` at the elevation threshold to `maximum_bandwidth` at
zenith, using each pass's maximum elevation.

The bundled scenario fixes the observer in Bengaluru, India, and evaluates a
24-hour interval near the static TLE epoch. It performs no network fetch.

To swap TLE sets:

1. Create a text file containing repeated name, TLE line 1, and TLE line 2
   triples.
2. Set `orbital.tle_file` in the scenario to its repository-relative path.
3. Set `orbital.start_utc` near that TLE set's epoch; old TLEs rapidly lose
   prediction quality.
4. Run `python -m northstar passes <scenario> --pretty` before simulation.

## LIVE-SIM channel shim

The live path consists of three independent operating-system processes:

```text
satellite_node.py  <-- TCP -->  channel_shim.py  <-- TCP -->  ground_station.py
       |                           |                           |
 source file                 Skyfield schedule          partial file + state
 retry/resume                loss/jitter/rate cap       SHA-256 verification
```

The sender never opens a direct connection to the receiver. The shim maps
Skyfield passes onto monotonic wall-clock time. Outside line-of-sight windows,
connections are immediately refused. During a pass, complete length-prefixed
OSPS frames are forwarded with an elevation-derived byte rate, seeded
packet loss, and jitter. At the pass deadline both sockets close.

The sender reconnects and begins with a metadata frame. The receiver reports
the first missing sequence number from its `.part` file and `.state.json`.
Transfer resumes there. On completion the receiver verifies SHA-256 and
atomically renames the partial file.

`TIME_SCALE` means simulation seconds per real second and defaults to `1`.
Bandwidth is multiplied by the same scale, preserving the pass's total
transfer capacity while shortening its wall-clock duration.

## Hardware adapter separation

- `radio_receiver/` handles sound-card input, channel metadata, decoder
  plugins, and synthetic WAV fixtures. Real AFSK/APT decoders are explicit
  stubs.
- `laser_link/` contains optical profiles and a separate software terminal.
  It models wavelength, pointing acquisition, cloud blocks, and optical
  bandwidth without importing audio code.

## CLI

```powershell
python -m pip install -r requirements.txt
python -m northstar run scenarios/interrupted_pass.json
python -m northstar run scenarios/interrupted_pass.json --pretty
python -m northstar passes scenarios/real_orbits.json --pretty
python -m northstar run scenarios/real_orbits.json --pretty
python -m unittest discover -s tests -v
python -m benchmarks.framing_benchmark --iterations 2000
```

The default command (`python -m northstar`) runs the bundled interrupted-pass
scenario. JSON Lines are the default output; `--pretty` provides compact
human-readable events.

## Test plan

- Round-trip frames with encryption and authentication.
- Reject bad magic, modified payloads, and wrong keys.
- Confirm high-priority messages are selected before bulk model data.
- Drop a chunk, age it past its timeout, and verify retransmission.
- Run the sample scenario and assert interruption, resume, and completion.
- Verify predicted passes are chronological, bounded by the simulation period,
  and non-overlapping for each satellite.
- Verify predicted passes enter the simulator through the unchanged contact
  interface.

## Known limitations and future work

- Replace the educational cipher with TLS 1.3/QUIC or an audited AEAD design.
- Model propagation, Doppler, RF weather, and asymmetric links.
- Add inter-satellite multi-hop routing and custody transfer.
- Persist forwarding state to disk and define crash consistency.
- Add forward error correction, selective ACK ranges, and adaptive coding.
- Specify canonical wire bytes in an Internet-Draft-style document.
- Benchmark against HTTP/3, QUIC, and Delay-Tolerant Networking bundles.
