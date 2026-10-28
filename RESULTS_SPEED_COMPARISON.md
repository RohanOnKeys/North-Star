# North Star Lab Results, Speed, and OSPS Protocol Comparison

> **Version note.** The measurements below were taken on June 19, 2026 with
> v0.2. Version 0.3 replaced the XOR cipher with ChaCha20-Poly1305, merged the
> two frame formats into one (version 2, 48 bytes of fixed overhead), let the
> simulator send several chunks per stream per tick, and made the shim close
> contacts promptly. The v0.2 numbers are kept as a historical record; the
> current figures are in [v0.3 results](#v03-results-october-2026).

## v0.3 results (October 2026)

Measured on October 28, 2026 in a Kaggle CPU session: Linux, 4 vCPU Intel Xeon
@ 2.20 GHz, Python 3.13.15, cryptography 50.0.1, Skyfield 1.53. The suite ran
twice; where the runs differ, both values are shown.

| Area | v0.2 | v0.3 |
|---|---|---|
| Automated tests | 17 passing | 32 passing |
| Real-orbit 150 KB model | Pass 9, 12.7 h | Pass 1, 210 s after it opens |
| Simulator wire bytes per 512 B chunk | 1,102 (46.5%) | 565 (90.6%) |
| Live-path efficiency at 32 KiB | 99.76% | 99.68% |
| Framing at 32 KiB, encode / decode | 5.3 / 5.2 MiB/s | 1,049 to 1,072 / 1,000 to 1,071 MiB/s |
| LIVE-SIM contacts used for 2 MiB | 6 | 3 or 4 |
| LIVE-SIM wall-clock duration | 35.8 s | 6.3 s or 16.4 s |
| Sender stalls on a closed contact | About 5 s each | None |
| SHA-256 match | Yes | Yes, same digest |

LIVE-SIM timing varies between runs because pass boundaries can cut a chunk
in half; it is a test-harness outcome, not a link-rate prediction.

Framing throughput by chunk size (first run, MiB/s):

| Chunk | Wire frame | Encode | Decode | Payload efficiency with ACK |
|---:|---:|---:|---:|---:|
| 1 KiB | 1,072 B | 148 | 191 | 90.78% |
| 4 KiB | 4,144 B | 401 | 406 | 97.52% |
| 16 KiB | 16,432 B | 896 | 930 | 99.37% |
| 32 KiB | 32,816 B | 1,078 | 1,071 | 99.68% |
| 128 KiB | 131,120 B | 1,274 | 1,120 | 99.92% |

At 32 KiB, decode now caps a single core at roughly 8.4 to 9.0 Gbit/s instead
of about 44 Mbit/s. Small chunks are dominated by per-frame Python overhead
rather than the cipher.

The new shim regression test was also run against the old close-only
behavior on Linux: it blocked for 5.0 s and timed out, reproducing the v0.2
stall, and it passes with the fix.

Reproduce with the commands at the end of this file.

## Executive summary (v0.2, June 2026)

The North Star lab demonstrated reliable file delivery across repeated,
Skyfield-predicted orbital contact windows using three separate programs and
real TCP sockets.

The strongest result is **continuity**, not universal speed superiority:

- a 2 MiB payload survived repeated complete connection loss;
- the receiver resumed from persisted chunk state;
- sender and receiver SHA-256 hashes matched;
- 32 KiB chunks provided about **99.76% application framing efficiency**
  (99.68% in v0.3, which adds a 12-byte nonce); and
- the educational pure-Python encryption reached only a few MiB/s, so it had
  to be replaced before high-rate RF or optical use (done in v0.3).

OSPS has not yet been benchmarked head-to-head against real HTTP/3,
QUIC, or BPv7 implementations under identical conditions. Therefore, no honest
claim like "X% faster than HTTP/3" can be made yet.

## What was tested (v0.2)

On June 19, 2026, LIVE-SIM ran three independent processes:

```text
northstar satellite  <---- TCP ---->  northstar shim  <---- TCP ---->  northstar ground
```

The channel used bundled TLEs and Skyfield passes over Bengaluru. It refused
connections outside line of sight, shaped bandwidth from elevation, injected
jitter and loss, and terminated sockets at pass boundaries.

The orbital clock used `TIME_SCALE=1200`. This compresses a day-long schedule
into roughly a minute while scaling bandwidth to preserve modeled capacity. It
does not make the result a measurement of real radio throughput.

## Achieved outcomes (v0.2)

| Outcome | Result |
|---|---|
| Payload | 2,097,152 bytes |
| Chunk size | 32,768 bytes |
| Chunks | 64 |
| Separate processes | Sender, channel, receiver |
| Contact behavior | Multiple predicted windows with full disconnections |
| Resume behavior | Continued from first missing persisted chunk |
| Receiver storage | `.part` file plus `.state.json` |
| Integrity | Sender and receiver SHA-256 matched |
| SHA-256 | `bdfddcc84d0cab83ad26c677b6e929532140d4583aef78e1fa944d8889f3a54d` |
| Wall-clock duration | Approximately 56.6 seconds |
| Wall-clock goodput | Approximately 37,068 B/s or 0.297 Mbit/s |
| Automated tests | 17 passing |

Wall-clock goodput includes compressed no-contact periods, retries,
reconnections, acknowledgements, jitter, loss, disk flushes, and hashing. It
is a test-harness outcome, not a spacecraft link-rate prediction.

## Wire efficiency (v0.2)

For each v0.2 32 KiB DATA chunk:

- OSPS frame header: 20 bytes;
- authentication tag: 16 bytes;
- socket packet-length field: 4 bytes; and
- ACK frame plus its packet-length field: 40 bytes.

Therefore:

```text
32,768 payload bytes
+   40 DATA framing bytes
+   40 ACK bytes
= 32,848 bytes
```

Payload efficiency:

```text
32,768 / 32,848 = 99.756%
```

That is 80 bytes of application-layer overhead per acknowledged 32 KiB chunk,
or about 0.244%. Metadata, reconnects, TCP/IP headers, retransmissions, and
radio error-correction overhead are not included.

v0.3 adds a 12-byte nonce to every frame, so a DATA frame and its ACK each
carry 52 bytes including the length field: 32,768 / 32,872 = 99.684%.

Smaller chunks reduce wasted retransmission after interruption but increase
percentage overhead. Larger chunks do the reverse.

## Local framing speed (v0.2)

Run:

```bash
python -m benchmarks.framing_benchmark --iterations 2000
```

The v0.2 development machine measured:

| Operation | Throughput |
|---|---:|
| Encode and educational encryption | 3.36 MiB/s |
| Authenticate, decrypt, and decode | 2.89 MiB/s |

This measures Python framing only. It excludes sockets, orbital gaps, disks,
and packet loss.

The v0.2 byte-by-byte XOR implementation would bottleneck links above
roughly 23 to 27 Mbit/s, which is unsuitable for serious S-band, X-band,
Ka-band, or optical throughput. Version 0.3 replaced it with native
ChaCha20-Poly1305.

## Comparison with available protocols

| Property | OSPS | HTTP/1.1 or HTTP/2 | HTTP/3 over QUIC | BPv7 / CCSDS BP |
|---|---|---|---|---|
| Primary purpose | Orbital streaming experiment | Web request/response | Secure modern web transport | Delay-tolerant networking |
| Durable resume after long outage | Built into live file flow | Application feature | Application feature | Core architectural concern |
| Receiver progress after restart | Yes | Not inherent | Not inherent | Persistent retention model |
| Multi-hop orbital routing | No | No | No | Yes |
| Independent multiplexed streams | Limited priority queues | HTTP/2 supports them | Strong support | Bundles rather than QUIC streams |
| Security today | Audited AEAD, static PSK, no key exchange | Mature TLS | TLS 1.3 integrated | BPSec and secure convergence layers |
| Congestion control | Simplified | Mature TCP | Mature QUIC | Usually convergence-layer dependent |
| Interoperability | None | Very high | High | Space/DTN standard |
| App framing efficiency at 32 KiB | 99.68% | Configuration-dependent | Configuration-dependent | Bundle-size dependent |

### Compared with HTTP over TCP

OSPS's demonstrated advantage is native resumable chunks and persisted
receive state. HTTP can resume data through range requests, ETags, multipart
uploads, or custom APIs, but the application must build those behaviors.

HTTP remains far ahead in security review, tooling, interoperability,
observability, deployment history, and performance engineering.

### Compared with HTTP/3 and QUIC

HTTP/3 uses QUIC for secure multiplexed streams, per-stream flow control, and
low-latency connection establishment. Independent streams prevent loss on one
stream from blocking every other stream. QUIC also supports connection
migration when a usable path changes.

Those are major advantages over OSPS's current stop-and-wait chunk
exchange.

Connection migration is not the same as persisting a partially received object
through a long period with no route and resuming it through a new application
connection. An application can build that over HTTP/3; the North Star lab
demonstrates it directly with OSPS.

There is currently **no measured speed win over HTTP/3**. A mature QUIC stack
would likely beat OSPS's stop-and-wait chunk exchange on a continuous link.

### Compared with BPv7 / CCSDS Bundle Protocol

BPv7 is the closest architectural comparison. It supports store-carry-forward
operation, bundle lifetimes, extension blocks, administrative records,
multiple convergence layers, and multi-hop delay-tolerant networks.

OSPS is smaller and easier to inspect in the North Star lab context, but it
lacks standardized endpoint IDs, bundle lifetimes, multi-hop routing, persistent
forwarding responsibility, BPSec, canonical CBOR, extension blocks, and
interoperability.

OSPS should eventually integrate with or move toward BPv7 rather than
claim to replace it.

## What efficiency has actually been demonstrated?

1. **Transfer efficiency:** acknowledged chunks are not resent after a pass
   ends.
2. **Scheduling efficiency:** urgent inference/control data can precede large
   model data.
3. **Framing efficiency:** approximately 99.68% payload at 32 KiB chunks
   (99.76% in v0.2).
4. **Operational efficiency:** a complete connection failure does not discard
   already persisted progress.

Not yet demonstrated:

- superior continuous-link throughput;
- better congestion control than QUIC;
- lower CPU use;
- standardized security;
- multi-hop routing; or
- production interoperability.

## Benchmark required for a real speed claim

A fair shootout must use the same payload, contact schedule, loss trace, and
machine for:

1. OSPS;
2. resumable HTTPS;
3. HTTP/3 with a production QUIC implementation;
4. a BPv7 implementation such as ION-DTN or DTNME; and
5. raw TCP as a control.

It should report goodput, total bytes, CPU, memory, disk writes, completion
time, reconnect cost, lost progress, and success rate. Until then, OSPS's
proven claim is **resilience**, not speed dominance.

## Reproduce the measurements

```bash
python -m unittest discover -s tests -v
python -m benchmarks.framing_benchmark --iterations 2000
```

Run LIVE-SIM using the three commands in [README.md](README.md).

## Primary references

- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [RFC 9000: QUIC](https://www.rfc-editor.org/rfc/rfc9000.html)
- [RFC 9171: Bundle Protocol Version 7](https://www.rfc-editor.org/rfc/rfc9171.html)
- [CCSDS 734.2-B-1: Bundle Protocol](https://public.ccsds.org/Pubs/734x2b1.pdf)
