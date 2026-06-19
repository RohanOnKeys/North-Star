# North Star Lab: Orbital Streaming Protocol Secure (OSPS) Explained

## The extremely short version

**North Star** is an experimental networking laboratory exploring the **Orbital
Streaming Protocol Secure (OSPS)** for moving data between orbital computers
and Earth.

The North Star lab explores this question:

> What if satellites had data centers onboard, and we needed to reliably move
> AI data between those satellites and Earth?

Normal internet protocols usually work best when both machines remain
connected. Satellites do not play by those rules. A satellite appears over the
horizon, communicates for a few minutes, disappears, and comes back later. OSPS
is designed to continue working through that mess.

It now includes both an in-process simulation and a live test using genuinely
separate programs connected through real TCP sockets. It is still a hobby and
research project: it is not currently flying satellites, operating a radio or
laser, or ready to replace HTTP.

---

## Why would anyone put a data center in orbit?

Imagine satellites that can do more than take pictures and send raw data home.
They might carry GPUs or other accelerators and perform work such as:

- analyzing Earth imagery before downloading it;
- running AI inference on sensor data;
- filtering unimportant information;
- coordinating autonomous spacecraft;
- storing large models and datasets; or
- sending processed results instead of enormous raw files.

This could reduce the amount of data that must be transmitted to Earth.

But orbital computers need a good way to exchange data. They may need to send:

- AI model weights;
- inference requests;
- inference results;
- telemetry;
- control messages; and
- software or configuration updates.

That is the territory the North Star lab explores.

---

## Why not just use HTTP?

HTTP is excellent for the normal internet. The normal internet usually gives
you a mostly continuous route between two computers.

An orbital link is different:

- The satellite may only be visible for a few minutes.
- It moves extremely quickly.
- Bandwidth changes throughout a pass.
- Latency may be significant.
- Frames can be lost.
- A transfer may be interrupted halfway through.
- The next useful connection might be hours later.

If a 10 GB AI model is 63% transferred when the satellite drops below the
horizon, starting again from zero would be painful.

OSPS divides data into chunks, remembers which chunks arrived, stores the rest,
and continues during another contact window.

That behavior is called **store-and-forward**.

---

## What happens in North Star?

Here is the broad flow:

```text
AI application
      |
      v
Ground station                       Satellite computer
+----------------+                   +----------------+
| OSPS endpoint  |  <--- link ---->  | OSPS endpoint  |
| queued data    |                   | queued data    |
+----------------+                   +----------------+
       \                               /
        \---- predicted orbital pass --/
```

### 1. We predict when satellites are visible

The North Star lab includes four representative Low Earth Orbit satellites
described using static **Two-Line Element sets**, usually called TLEs.

The **Skyfield** Python library uses those TLEs and the SGP4 orbit model to
predict when each satellite rises above a ground station in Bengaluru, India.

A pass counts as usable when the satellite is more than 10 degrees above the
horizon. For each pass, the North Star lab calculates:

- when the pass begins;
- when it ends;
- its duration;
- the maximum elevation; and
- an estimated bandwidth.

Higher passes receive a larger estimated bandwidth because a satellite high in
the sky generally has a better link than one barely above the horizon.

The orbital positions and contact times are computed using real orbital
mechanics. Radio conditions and bandwidth are still simplified estimates.

### 2. The ground station and satellite authenticate each other

When a contact opens, both sides perform a simulated handshake.

They use a shared secret key and HMAC-SHA256 proofs to check that the other
side knows the same secret. Data is sent only after both sides are
authenticated.

### 3. Messages enter priority queues

OSPS supports several workload types:

| Workload | Example | Priority |
|---|---|---:|
| Control | Tell a node to change behavior | Highest |
| Inference | Ask an orbital model a question | High |
| Result | Return an AI answer | High |
| Telemetry | Report temperatures and status | Medium |
| Model | Upload large model weights | Lowest |

This means a tiny urgent request does not have to sit behind a huge model
upload.

OSPS also occasionally serves lower-priority data so that a model transfer
cannot be ignored forever.

### 4. Large messages become chunks

A message is divided into smaller pieces. Every chunk receives:

- a stream ID identifying its parent message;
- a sequence number identifying its position; and
- the total number of chunks in the message.

The receiver stores chunks and puts them back in order after all of them
arrive.

### 5. Every chunk travels inside an OSPS frame

An OSPS frame contains:

```text
+---------+---------+------+-----------+----------+---------+------+
| "NSTR"  | Version | Type | Stream ID | Sequence | Payload | HMAC |
+---------+---------+------+-----------+----------+---------+------+
```

The magic value `"NSTR"` identifies the protocol. The version allows the
format to evolve. The HMAC detects modification or corruption.

The North Star lab encrypts payloads with a small educational construction
based on HMAC-generated bytes and XOR.

That encryption is useful for demonstrating protocol behavior, but it is
**not production cryptography**. A real implementation would need an audited
encryption system such as an established AEAD construction.

### 6. The receiver acknowledges successful chunks

When a chunk arrives, the receiver returns an **ACK**, short for
acknowledgement.

If the sender does not receive an ACK, it waits for a timeout and tries that
chunk again. Duplicate chunks are safe: the receiver simply acknowledges them
again.

### 7. The satellite disappears dramatically

When a contact closes, both endpoints disconnect.

They do not forget:

- queued messages;
- chunks already acknowledged;
- chunks still missing;
- retry counts; or
- partially reconstructed messages.

When a later pass opens, the endpoints authenticate again and continue from
the remaining chunks.

This is the heart of the project.

---

## Is it only a simulation?

Not anymore.

The North Star lab now has a **LIVE-SIM** made of three standalone programs:

```text
satellite_node.py  <---- TCP ---->  channel_shim.py  <---- TCP ---->  ground_station.py
       sender                       orbital channel                     receiver
```

These are separate operating-system processes. The satellite sender cannot
talk directly to the ground receiver; every byte must pass through the channel
shim.

The channel shim reads the real Skyfield pass schedule and turns it into
wall-clock connectivity:

- outside a predicted pass, connections are refused or dropped;
- during a pass, real socket traffic is forwarded;
- bandwidth is limited using the pass elevation;
- light jitter and packet loss are injected; and
- when the pass ends, the connection closes—even mid-transfer.

The satellite process keeps trying. On every reconnection, the ground station
reports the first chunk it still needs. The sender resumes from there instead
of restarting.

The receiver saves progress in a partial file and a state file. Once every
chunk arrives, it calculates SHA-256, compares it with the sender's digest,
and only then promotes the partial file to the finished output.

This was tested with a 2 MiB payload across multiple predicted windows. Both
ends produced this SHA-256:

```text
bdfddcc84d0cab83ad26c677b6e929532140d4583aef78e1fa944d8889f3a54d
```

LIVE-SIM logs use real UTC timestamps instead of simulated ticks.

### What does TIME_SCALE do?

The real pass schedule spans a full day. Waiting all day to test two megabytes
would be heroic, but not especially practical.

`TIME_SCALE` compresses orbital time. At `1200`, 1,200 simulated seconds pass
during one real second. The North Star lab scales bandwidth by the same factor
so each shortened pass keeps roughly the same total transfer capacity.

---

## Is the orbital mechanics actually real?

Yes, with an important asterisk.

The North Star lab uses:

- real SGP4 orbit propagation through Skyfield;
- standard TLE input;
- a real latitude, longitude, and elevation for the ground station;
- real rise, culmination, and set calculations; and
- a configurable minimum elevation.

The North Star lab does **not** yet model:

- antennas;
- frequency bands;
- atmospheric conditions;
- Doppler shift;
- interference;
- detailed RF link budgets;
- spacecraft attitude;
- ground-station scheduling conflicts; or
- accurate live satellite positions.

The bundled TLEs are fixed representative simulation data. Static inputs make
tests reproducible, but they must not be used to locate real spacecraft today.

---

## How is this related to space networking standards?

Real delay-tolerant space networking already has serious standards, especially
the **CCSDS Bundle Protocol** and IETF **Bundle Protocol Version 7**.

Bundle Protocol treats data as self-contained bundles that can be stored,
carried, and forwarded through multiple nodes. It supports a much richer model
for addressing, lifetimes, extension blocks, security, reporting, routing, and
interoperability.

OSPS borrows the general store-and-forward mindset, but it is deliberately much
smaller:

| OSPS in North Star lab | Bundle Protocol |
|---|---|
| Two simulated endpoints | Multi-hop delay-tolerant network |
| Per-chunk ACKs | Full bundle processing model |
| In-memory state | Persistent bundle retention |
| Local stream IDs | Standard endpoint identifiers |
| Custom experimental frames | Standardized bundle format |
| Educational security | Standard Bundle Protocol Security |

The North Star lab is therefore not claiming, "We invented space networking."

It is asking, "Can we build a small understandable playground for secure,
priority-aware AI streaming over real predicted orbital contacts?"

That is a much more honest and useful goal.

---

## What parts of North Star exist right now?

The North Star lab currently contains:

- a binary frame encoder and decoder;
- authenticated, simulated payload encryption;
- a mutual handshake;
- workload priority queues;
- message chunking and reassembly;
- ACKs, retries, and duplicate handling;
- a simple congestion window;
- store-and-forward state across contacts;
- manually configured contact windows;
- real TLE-based contact prediction;
- structured JSON and readable terminal logs;
- an interrupted-pass demonstration;
- a real-orbit demonstration;
- a three-process live socket demonstration;
- disk-backed receive progress and SHA-256 verification;
- a separate radio/audio-jack receiver scaffold;
- three generated synthetic WAV fixtures;
- decoder plugins that clearly reject unfinished modes;
- a separate laser-link software scaffold;
- optical profiles with acquisition time and cloud-blocked passes;
- unit tests; and
- requirements, architecture, and formal protocol documentation.

---

## Why are the radio and laser programs separate?

Because they are physically different systems.

### Radio/audio-jack path

The `radio_receiver/` program is for a possible future VHF or UHF receiver
whose demodulated audio output is connected to a PC microphone or line-in
jack.

It currently provides:

- a registry containing frequency, band, mode, and notes;
- optional sound-card device listing and WAV recording;
- a pluggable decoder interface;
- three generated tone-based WAV fixtures; and
- a real decoder for those synthetic tones only.

AFSK1200 and APT return a clear **not implemented** result. The North Star lab
does not pretend that recognizing a test tone means it can decode the ISS or a
weather satellite.

An audio jack can only carry audio from a radio that already received and
demodulated a suitable VHF/UHF signal. It cannot directly receive S-band,
X-band, Ka-band, or an optical link.

### Laser/optical path

The `laser_link/` program is completely separate. It models:

- optical wavelength profiles, currently centered on 1550 nm;
- much higher nominal bandwidth;
- pointing and acquisition time;
- cloud-sensitive ground links; and
- orbital windows that can be explicitly blocked by weather.

It also has its own software socket sender and receiver.

It does **not** operate a real laser, telescope, tracking mount, optical modem,
photodetector, beacon, or safety system. Real free-space optical work requires
specialized hardware, precision pointing, legal approval, eye and aviation
safety controls, and weather-aware operations.

Keeping the programs separate prevents the North Star lab from assuming every
orbital channel is slow VHF audio. A future link can be radio or optical while
the chunking and store-and-forward logic above it remains the same.

The radio CLI now makes that choice explicit:

```powershell
# No hardware: decode an existing WAV fixture or recording
python -m radio_receiver.cli receive --source wav --input radio_receiver/fixtures/synthetic_1000hz.wav --mode SYNTHETIC_TONE

# Hardware: record from sound-device input 0, then pass it to a decoder
python -m radio_receiver.cli receive --source hardware --device 0 --seconds 15 --recording-output capture.wav --mode AFSK1200
```

`--source wav` needs no receiver hardware. `--source hardware` uses the
optional `sounddevice` package and a real PC audio input. Capturing audio
successfully does not mean its selected decoder is implemented; unfinished
modes still report failure honestly.

---

## What does "secure" mean here?

At the moment, "secure" means that OSPS demonstrates:

- mutual possession of a pre-shared key;
- payload scrambling;
- frame authentication;
- integrity checks; and
- rejection of frames modified with the wrong key.

It does not yet mean production-grade security.

Before OSPS could protect real spacecraft, it would need:

- standard authenticated encryption;
- proper session-key derivation;
- unique nonces;
- key rotation and revocation;
- replay protection;
- identity management;
- forward secrecy where practical;
- secure key storage;
- threat modeling;
- independent review; and
- extensive hostile-input testing.

The current design is a protocol laboratory, not a security product.

---

## Run it yourself

Install Python 3.11 or newer, then install the one direct dependency:

```powershell
python -m pip install -r requirements.txt
```

See the predicted satellite passes:

```powershell
python -m northstar passes scenarios/real_orbits.json --pretty
```

Run OSPS across those passes:

```powershell
python -m northstar run scenarios/real_orbits.json --pretty
```

Run the deliberately interrupted test scenario:

```powershell
python -m northstar run scenarios/interrupted_pass.json --pretty
```

Run all automated tests:

```powershell
python -m unittest discover -s tests -v
```

---

## What results have we actually achieved?

The North Star lab has completed a real three-process LIVE-SIM transfer with:

- a 2 MiB payload;
- 64 chunks of 32 KiB each;
- repeated complete socket disconnections;
- multiple real Skyfield-predicted orbital windows;
- disk-backed receive progress;
- reconnection and continuation from the first missing chunk; and
- matching sender and receiver SHA-256 hashes.

The verified hash was:

```text
bdfddcc84d0cab83ad26c677b6e929532140d4583aef78e1fa944d8889f3a54d
```

The compressed live run took roughly 56.6 wall-clock seconds. That gives an
end-to-end goodput of about 37,068 bytes per second, or 0.297 Mbit/s. This
number includes compressed no-contact gaps, retries, reconnections, disk
flushes, acknowledgements, jitter, loss, and hashing. It is **not** a claim
that a real satellite radio would run at that speed.

### How efficient is the frame format?

For every 32,768-byte DATA chunk, the current live OSPS protocol adds:

- 40 bytes around the DATA payload; and
- 40 bytes for its ACK.

That produces:

```text
32,768 / 32,848 = 99.756% payload efficiency
```

So the OSPS application framing overhead is about 0.244% at the current
chunk size. TCP/IP, reconnect metadata, retransmissions, radio modulation,
forward error correction, and antenna/link losses are outside that number.

### How fast is the Python codec?

This benchmark:

```powershell
python -m benchmarks.framing_benchmark --iterations 2000
```

measured approximately:

| Operation | Current result |
|---|---:|
| Encode and educational encryption | 3.36 MiB/s |
| Authenticate, decrypt, and decode | 2.89 MiB/s |

That is enough for this experiment, but it is too slow for serious
high-throughput RF or laser links. The educational byte-by-byte cipher must be
replaced with audited native cryptography.

### Is OSPS faster than HTTP/3, QUIC, or Bundle Protocol?

We do not know yet.

OSPS has **not** been benchmarked against production HTTP/3, QUIC, or BPv7
implementations under the same pass schedule and packet-loss trace. Claiming a
percentage speed advantage would be made-up marketing.

What has been demonstrated is different:

| OSPS strength today | Meaning |
|---|---|
| Store-and-forward resume | A vanished link does not erase received progress |
| Priority scheduling | Urgent AI traffic can precede model bulk data |
| 99.756% app framing efficiency | Large chunks spend little space on OSPS headers |
| Persisted receiver state | A new connection can continue an old transfer |

HTTP can provide resumable uploads through application features such as range
requests, ETags, multipart APIs, or custom endpoints. HTTP/3 and QUIC have far
more mature security, congestion control, multiplexing, and continuous-link
performance. BPv7 is a real delay-tolerant networking standard with multi-hop
forwarding, lifetimes, extension blocks, and interoperable security.

OSPS's honest current claim is:

> It reliably resumes prioritized data across predicted orbital outages.

It cannot honestly claim:

> It is faster than every existing protocol.

See [RESULTS_SPEED_COMPARISON.md](RESULTS_SPEED_COMPARISON.md) for the complete
measurements, limitations, and fair-comparison plan.

---

## Run the real three-process test

Open three terminals from the North Star lab project folder.

Terminal 1 — start the receiver:

```powershell
python ground_station.py --output-dir received
```

Terminal 2 — start the orbital channel:

```powershell
python channel_shim.py --time-scale 1200
```

Terminal 3 — generate and send a 2 MiB dummy model:

```powershell
python satellite_node.py model_weights.bin --generate-bytes 2097152 --retry-delay 0.02
```

The orbital clock waits for the first sender connection before starting, so
taking a little time to open the terminals does not consume the early passes.

When the transfer completes, compare the hashes for independent confirmation:

```powershell
Get-FileHash model_weights.bin
Get-FileHash received/model_weights.bin
```

---

## Try the radio scaffold without hardware

Generate synthetic WAV fixtures:

```powershell
python -m radio_receiver.cli generate-fixtures
```

Decode one supported synthetic tone:

```powershell
python -m radio_receiver.cli decode radio_receiver/fixtures/synthetic_1000hz.wav --mode SYNTHETIC_TONE
```

Ask for an unfinished real mode:

```powershell
python -m radio_receiver.cli decode radio_receiver/fixtures/synthetic_1000hz.wav --mode AFSK1200
```

The final command deliberately reports that AFSK1200 is not implemented.

Live sound-card capture later requires:

```powershell
python -m pip install -r requirements-radio.txt
python -m radio_receiver.cli list-devices
```

---

## Try the separate laser scaffold

Inspect optical windows while pretending pass number 1 is cloud-blocked:

```powershell
python -m laser_link.cli profile --blocked-pass 1
```

Run its standalone software terminal:

```powershell
# Terminal 1
python -m laser_link.cli receive

# Terminal 2
python -m laser_link.cli send laser_payload.bin --generate-bytes 1048576
```

This tests the software boundary only. No photons are harmed or even mildly
inconvenienced.

---

## How to read the logs without losing your mind

A readable event might look roughly like this:

```text
T+003s chunk_acked GQ=10 SQ=0 source=ground workload=inference
```

That means:

- `T+003s`: three simulated seconds have passed;
- `chunk_acked`: a data chunk arrived and was acknowledged;
- `GQ=10`: ten ground-station chunks remain queued;
- `SQ=0`: the satellite has no outgoing chunks queued;
- `source=ground`: the ground station sent it; and
- `workload=inference`: it belongs to an AI inference request.

Other useful events include:

- `contact_opened`;
- `session_established`;
- `frame_dropped`;
- `contact_interrupted`;
- `contact_closed`; and
- `stream_completed`.

If a stream begins during one pass and completes during another, the
store-and-forward system did its job.

---

## Where the project should go next

The most meaningful next steps are:

1. Replace the educational crypto with standard, audited security.
2. Extend the disk-backed live receiver into durable sender queues and
   crash-safe session recovery.
3. Add multiple satellites, ground stations, and inter-satellite relays.
4. Use proper contact-aware routing.
5. Build a realistic RF link budget instead of estimating bandwidth from
   elevation alone.
6. Add message expiration, cancellation, selective acknowledgements, and
   forward error correction.
7. Compare performance against HTTP/3, QUIC, and Bundle Protocol.
8. Move toward BPv7 compatibility instead of inventing incompatible features
   that already exist in mature standards.
9. Implement and validate real radio decoders against legally captured audio.
10. Integrate an SDR or radio modem instead of relying only on audio output.
11. Develop an optical terminal adapter only after suitable hardware, safety,
    tracking, and legal requirements are understood.

---

## The big idea

The North Star lab is not currently "the future replacement for HTTP."

It is the beginning of an experiment around a real problem:

> How should AI systems exchange large, urgent, and sensitive data when the
> network repeatedly disappears underneath them?

The project combines orbital pass prediction with a small, inspectable OSPS
protocol that can prioritize useful work, survive interruption, and resume
later.

That is the North Star lab: not magic space internet yet, but a working
laboratory for figuring out what magic space internet might require.
