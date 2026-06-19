# North Star Results, Speed, and Protocol Comparison

## Executive summary

North Star demonstrated reliable file delivery across repeated,
Skyfield-predicted orbital contact windows using three separate programs and
real TCP sockets.

The strongest result is **continuity**, not universal speed superiority:

- a 2 MiB payload survived repeated complete connection loss;
- the receiver resumed from persisted chunk state;
- sender and receiver SHA-256 hashes matched;
- current 32 KiB chunks provide about **99.76% application framing
  efficiency**; and
- the educational pure-Python encryption reaches only a few MiB/s, so it must
  be replaced before high-rate RF or optical use.

North Star has not yet been benchmarked head-to-head against real HTTP/3,
QUIC, or BPv7 implementations under identical conditions. Therefore, no honest
claim like "X% faster than HTTP/3" can be made yet.

## What was tested

On June 19, 2026, LIVE-SIM ran three independent processes:

```text
satellite_node.py  <---- TCP ---->  channel_shim.py  <---- TCP ---->  ground_station.py
```

The channel used bundled TLEs and Skyfield passes over Bengaluru. It refused
connections outside line of sight, shaped bandwidth from elevation, injected
jitter and loss, and terminated sockets at pass boundaries.

The orbital clock used `TIME_SCALE=1200`. This compresses a day-long schedule
into roughly a minute while scaling bandwidth to preserve modeled capacity. It
does not make the result a measurement of real radio throughput.

## Achieved outcomes

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

## Wire efficiency

For each current 32 KiB DATA chunk:

- North Star frame header: 20 bytes;
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

Smaller chunks reduce wasted retransmission after interruption but increase
percentage overhead. Larger chunks do the reverse.

## Local framing speed

Run:

```powershell
python -m benchmarks.framing_benchmark --iterations 2000
```

The current development machine measured:

| Operation | Throughput |
|---|---:|
| Encode and educational encryption | 3.36 MiB/s |
| Authenticate, decrypt, and decode | 2.89 MiB/s |

This measures Python framing only. It excludes sockets, orbital gaps, disks,
and packet loss.

The current byte-by-byte XOR implementation would bottleneck links above
roughly 23–27 Mbit/s. It is unsuitable for serious S-band, X-band, Ka-band,
or optical throughput. Production work needs audited native cryptography.

## Comparison with available protocols

| Property | North Star | HTTP/1.1 or HTTP/2 | HTTP/3 over QUIC | BPv7 / CCSDS BP |
|---|---|---|---|---|
| Primary purpose | Orbital streaming experiment | Web request/response | Secure modern web transport | Delay-tolerant networking |
| Durable resume after long outage | Built into live file flow | Application feature | Application feature | Core architectural concern |
| Receiver progress after restart | Yes | Not inherent | Not inherent | Persistent retention model |
| Multi-hop orbital routing | No | No | No | Yes |
| Independent multiplexed streams | Limited priority queues | HTTP/2 supports them | Strong support | Bundles rather than QUIC streams |
| Security today | Educational only | Mature TLS | TLS 1.3 integrated | BPSec and secure convergence layers |
| Congestion control | Simplified | Mature TCP | Mature QUIC | Usually convergence-layer dependent |
| Interoperability | None | Very high | High | Space/DTN standard |
| Current app framing efficiency | 99.76% | Configuration-dependent | Configuration-dependent | Bundle-size dependent |

### Compared with HTTP over TCP

North Star's demonstrated advantage is native resumable chunks and persisted
receive state. HTTP can resume data through range requests, ETags, multipart
uploads, or custom APIs, but the application must build those behaviors.

HTTP remains far ahead in security review, tooling, interoperability,
observability, deployment history, and performance engineering.

### Compared with HTTP/3 and QUIC

HTTP/3 uses QUIC for secure multiplexed streams, per-stream flow control, and
low-latency connection establishment. Independent streams prevent loss on one
stream from blocking every other stream. QUIC also supports connection
migration when a usable path changes.

Those are major advantages over North Star's current stop-and-wait chunk
exchange.

Connection migration is not the same as persisting a partially received object
through a long period with no route and resuming it through a new application
connection. An application can build that over HTTP/3; North Star demonstrates
it directly.

There is currently **no measured speed win over HTTP/3**. A mature QUIC stack
would likely beat the current Python codec on a continuous link.

### Compared with BPv7 / CCSDS Bundle Protocol

BPv7 is the closest architectural comparison. It supports store-carry-forward
operation, bundle lifetimes, extension blocks, administrative records,
multiple convergence layers, and multi-hop delay-tolerant networks.

North Star is smaller and easier to inspect, but it lacks standardized endpoint
IDs, bundle lifetimes, multi-hop routing, persistent forwarding responsibility,
BPSec, canonical CBOR, extension blocks, and interoperability.

North Star should eventually integrate with or move toward BPv7 rather than
claim to replace it.

## What efficiency has actually been demonstrated?

1. **Transfer efficiency:** acknowledged chunks are not resent after a pass
   ends.
2. **Scheduling efficiency:** urgent inference/control data can precede large
   model data.
3. **Framing efficiency:** approximately 99.76% payload at 32 KiB chunks.
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

1. North Star;
2. resumable HTTPS;
3. HTTP/3 with a production QUIC implementation;
4. a BPv7 implementation such as ION-DTN or DTNME; and
5. raw TCP as a control.

It should report goodput, total bytes, CPU, memory, disk writes, completion
time, reconnect cost, lost progress, and success rate. Until then, North
Star's proven claim is **resilience**, not speed dominance.

## Reproduce the measurements

```powershell
python -m unittest discover -s tests -v
python -m benchmarks.framing_benchmark --iterations 2000
```

Run LIVE-SIM using the three commands in [README.md](README.md).

## Primary references

- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html)
- [RFC 9000 — QUIC](https://www.rfc-editor.org/rfc/rfc9000.html)
- [RFC 9171 — Bundle Protocol Version 7](https://www.rfc-editor.org/rfc/rfc9171.html)
- [CCSDS 734.2-B-1 — Bundle Protocol](https://public.ccsds.org/Pubs/734x2b1.pdf)
